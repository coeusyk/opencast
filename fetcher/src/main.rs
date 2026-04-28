mod models;
mod client;

use clap::Parser;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION};
use reqwest::Client;
use serde::Deserialize;
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
}


#[derive(Deserialize, Debug)]
struct OpeningConfig {
    eco: String,
    #[allow(dead_code)]
    name: String,
    moves: String,
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


#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();

    let token = std::env::var("LICHESS_TOKEN").ok();
    let client = {
        let mut headers = HeaderMap::new();
        headers.insert(
            reqwest::header::USER_AGENT,
            HeaderValue::from_static("opencast-fetcher/0.1"),
        );
        if let Some(ref t) = token {
            let value = HeaderValue::from_str(&format!("Bearer {}", t))?;
            headers.insert(AUTHORIZATION, value);
        }
        Client::builder().default_headers(headers).build()?
    };

    let config_raw = fs::read_to_string("../openings.json")?;
    let openings: Vec<OpeningConfig> = serde_json::from_str(&config_raw)?;

    let months = generate_months(&args.from, &args.to);

    println!(
        "Fetching {} openings × {} months = {} requests",
        openings.len(),
        months.len(),
        openings.len() * months.len()
    );

    for opening in &openings {
        for month in &months {
            client::fetch_opening_month(
                &client,
                &opening.moves,
                month,
                args.rating,
                &args.speed,
                &opening.eco,
            )
            .await?;
        }
    }

    println!("Done.");
    Ok(())
}