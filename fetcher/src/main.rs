mod client;

use clap::Parser;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION};
use reqwest::Client;
use serde::Deserialize;
use std::collections::HashSet;
use std::fs;


#[derive(Parser, Debug)]
#[command(name = "opencast-fetcher")]
struct Args {
    #[arg(long, default_value = "2023-01")]
    from: String,

    #[arg(long, default_value = "2026-03")]
    to: String,

    #[arg(long, default_value_t = 2000)]
    rating: u32,

    #[arg(long, default_value = "blitz")]
    speed: String,

    /// Skip writing any month whose total games (white+draws+black) is below this threshold.
    #[arg(long, default_value_t = 0)]
    min_games: u64,

    /// Early-stop an ECO when below-min skipped months reach this ratio of the requested range.
    /// Example: 0.4 over a 40-month range stops after 16 below-min skips.
    #[arg(long, default_value_t = 0.4)]
    max_skipped_ratio: f64,
}


#[derive(Debug, Deserialize)]
struct CatalogRow {
    eco: String,
    #[allow(dead_code)]
    name: String,
    #[allow(dead_code)]
    eco_group: String,
    moves: String,
    is_tracked_core: String,
    is_long_tail: String,
    #[allow(dead_code)]
    model_tier: String,
}

impl CatalogRow {
    fn is_active(&self) -> bool {
        let core = self.is_tracked_core.trim().eq_ignore_ascii_case("true");
        let tail  = self.is_long_tail.trim().eq_ignore_ascii_case("true");
        core || tail
    }
}


fn generate_months(from: &str, to: &str) -> Vec<String> {
    let mut months = Vec::new();
    let (mut year, mut month) = parse_ym(from);
    let (end_year, end_month) = parse_ym(to);

    while (year, month) <= (end_year, end_month) {
        months.push(format!("{:04}-{:02}", year, month));
        month += 1;
        if month > 12 {
            month = 1;
            year += 1;
        }
    }
    months
}

fn parse_ym(s: &str) -> (u32, u32) {
    let parts: Vec<u32> = s.split('-').map(|x| x.parse().unwrap()).collect();
    (parts[0], parts[1])
}


fn load_openings_from_catalog(catalog_path: &str) -> Result<Vec<(String, String)>, Box<dyn std::error::Error>> {
    let mut reader = csv::Reader::from_path(catalog_path)?;
    let mut openings: Vec<(String, String)> = Vec::new();

    for result in reader.deserialize::<CatalogRow>() {
        match result {
            Ok(row) if row.is_active() && !row.moves.is_empty() => {
                openings.push((row.eco, row.moves));
            }
            Ok(_) => {}
            Err(e) => eprintln!("Warning: skipping catalog row: {e}"),
        }
    }
    Ok(openings)
}


#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();
    let user_agent = format!("opencast-fetcher/{}", env!("CARGO_PKG_VERSION"));

    let token = std::env::var("LICHESS_TOKEN").ok();
    let client = {
        let mut headers = HeaderMap::new();
        headers.insert(reqwest::header::USER_AGENT, HeaderValue::from_str(&user_agent)?);
        if let Some(ref t) = token {
            let value = HeaderValue::from_str(&format!("Bearer {}", t))?;
            headers.insert(AUTHORIZATION, value);
        }
        Client::builder().default_headers(headers).build()?
    };

    // Prefer catalog CSV over legacy openings.json
    let catalog_path = "../data/openings_catalog.csv";
    let mut openings: Vec<(String, String)> = if fs::metadata(catalog_path).is_ok() {
        println!("Loading openings from catalog: {catalog_path}");
        load_openings_from_catalog(catalog_path)?
    } else {
        println!("Catalog not found — falling back to openings.json");
        let raw = fs::read_to_string("../openings.json")?;
        let entries: Vec<serde_json::Value> = serde_json::from_str(&raw)?;
        entries
            .into_iter()
            .filter_map(|v| {
                let eco   = v["eco"].as_str()?.to_string();
                let moves = v["moves"].as_str()?.to_string();
                Some((eco, moves))
            })
            .collect()
    };

    // Honour OPENCAST_ECO_LIMIT for local development / quick runs
    if let Ok(limit_str) = std::env::var("OPENCAST_ECO_LIMIT") {
        if let Ok(limit) = limit_str.parse::<usize>() {
            if limit < openings.len() {
                println!("OPENCAST_ECO_LIMIT={limit} — capping to {limit} openings");
                openings.truncate(limit);
            }
        }
    }

    // Optional precise filter for bootstrap runs: only fetch these ECO codes.
    if let Ok(eco_only) = std::env::var("OPENCAST_ECO_ONLY") {
        let allowed: HashSet<String> = eco_only
            .split(',')
            .map(|s| s.trim().to_uppercase())
            .filter(|s| !s.is_empty())
            .collect();
        if !allowed.is_empty() {
            openings.retain(|(eco, _)| allowed.contains(eco));
            println!(
                "OPENCAST_ECO_ONLY set — filtered openings to {} entries",
                openings.len()
            );
        }
    }

    let months = generate_months(&args.from, &args.to);

    println!(
        "Fetching {} openings × {} months = {} requests",
        openings.len(),
        months.len(),
        openings.len() * months.len()
    );

    for (eco, moves) in &openings {
        let total_months = months.len();
        let skip_cutoff = if args.max_skipped_ratio > 0.0 && total_months > 0 {
            ((args.max_skipped_ratio * total_months as f64).ceil() as usize).max(1)
        } else {
            usize::MAX
        };
        let mut below_min_skips: usize = 0;

        for month in &months {
            let outcome = client::fetch_opening_month(
                &client,
                moves,
                month,
                args.rating,
                &args.speed,
                eco,
                args.min_games,
            )
            .await?;

            if matches!(outcome, client::MonthFetchOutcome::SkippedBelowMinGames) {
                below_min_skips += 1;
                if below_min_skips >= skip_cutoff {
                    println!(
                        "Early-stopping {} after {} below-min skips (ratio limit {:.3}, total months {})",
                        eco,
                        below_min_skips,
                        args.max_skipped_ratio,
                        total_months
                    );
                    let output_path = format!("../data/raw/{}/{}.json", &eco[0..1], eco);
                    if fs::metadata(&output_path).is_ok() {
                        match fs::remove_file(&output_path) {
                            Ok(_) => println!("Removed {} due to early-stop verdict", output_path),
                            Err(e) => eprintln!("Warning: could not remove {}: {}", output_path, e),
                        }
                    }
                    let tmp_path = format!("../data/raw/{}/{}.tmp.json", &eco[0..1], eco);
                    if fs::metadata(&tmp_path).is_ok() {
                        let _ = fs::remove_file(&tmp_path);
                    }
                    break;
                }
            }
        }
    }

    println!("Done.");
    Ok(())
}