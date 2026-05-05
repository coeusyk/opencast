use reqwest::Client;
use serde_json::{json, Value};
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MonthFetchOutcome {
    Fetched,
    AlreadyPresent,
    SkippedZeroGames,
    SkippedBelowMinGames,
}

fn write_consolidated(
    consolidated: &Value,
    tmp_path: &str,
    output_path: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    if let Some(parent) = Path::new(tmp_path).parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(tmp_path, serde_json::to_string_pretty(consolidated)?)?;
    fs::rename(tmp_path, output_path)?;
    Ok(())
}

fn mark_skipped_month(consolidated: &mut Value, month: &str, reason: &str) {
    if consolidated.get("_meta").is_none() {
        consolidated["_meta"] = json!({});
    }
    if !consolidated["_meta"]["skipped_months"].is_object() {
        consolidated["_meta"]["skipped_months"] = json!({});
    }
    consolidated["_meta"]["skipped_months"][month] = Value::String(reason.to_string());
}

pub async fn fetch_opening_month(
    client: &Client,
    moves: &str,
    month: &str,
    rating: u32,
    speed: &str,
    eco: &str,
    min_games: u64,
) -> Result<MonthFetchOutcome, Box<dyn std::error::Error>> {
    let eco_group = &eco[0..1];
    let output_path = format!("../data/raw/{}/{}.json", eco_group, eco);
    let tmp_path    = format!("../data/raw/{}/{}.tmp.json", eco_group, eco);

    // Read existing consolidated file or start a fresh structure.
    let mut consolidated: Value = if Path::new(&output_path).exists() {
        let content = fs::read_to_string(&output_path)?;
        serde_json::from_str(&content)?
    } else {
        json!({ "eco": eco, "months": {} })
    };
    let had_real_months = consolidated["months"]
        .as_object()
        .map(|m| !m.is_empty())
        .unwrap_or(false);

    // Skip months that are already present in the file.
    if !consolidated["months"][month].is_null() {
        println!("Skipping {} {} (already present)", eco, month);
        return Ok(MonthFetchOutcome::AlreadyPresent);
    }

    let url = "https://explorer.lichess.ovh/lichess";

    let response = client
        .get(url)
        .query(&[
            ("play", moves),
            ("speeds", speed),
            ("ratings", &rating.to_string()),
            ("since", month),
            ("until", month),
        ])
        .send()
        .await?;

    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        return Err(format!("HTTP {} for {} {}: {}", status, eco, month, body).into());
    }

    // Store the full Lichess response as-is (preserves topGames, opening, etc.).
    let month_data: Value = response.json().await?;

    // Skip months where Lichess hasn't indexed the data yet (returns 0 games).
    let total_games = month_data["white"].as_u64().unwrap_or(0)
        + month_data["draws"].as_u64().unwrap_or(0)
        + month_data["black"].as_u64().unwrap_or(0);
    if total_games == 0 {
        if had_real_months {
            mark_skipped_month(&mut consolidated, month, "zero_games");
            write_consolidated(&consolidated, &tmp_path, &output_path)?;
        }
        println!("Skipping {} {} (0 games — not yet indexed)", eco, month);
        tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
        return Ok(MonthFetchOutcome::SkippedZeroGames);
    }
    if min_games > 0 && total_games < min_games {
        if had_real_months {
            mark_skipped_month(&mut consolidated, month, "below_min_games");
            write_consolidated(&consolidated, &tmp_path, &output_path)?;
        }
        println!("Skipping {} {} ({} games < {} threshold)", eco, month, total_games, min_games);
        tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
        return Ok(MonthFetchOutcome::SkippedBelowMinGames);
    }

    consolidated["months"][month] = month_data;

    // Atomic write: write to .tmp then rename to avoid corruption on crash.
    write_consolidated(&consolidated, &tmp_path, &output_path)?;

    println!("Fetched {} {}", eco, month);

    tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;

    Ok(MonthFetchOutcome::Fetched)
}