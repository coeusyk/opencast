use reqwest::Client;
use serde_json::{json, Value};
use std::fs;
use std::path::Path;

pub async fn fetch_opening_month(
    client: &Client,
    moves: &str,
    month: &str,
    rating: u32,
    speed: &str,
    eco: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let output_path = format!("../data/raw/{}.json", eco);
    let tmp_path    = format!("../data/raw/{}.tmp.json", eco);

    // Read existing consolidated file or start a fresh structure.
    let mut consolidated: Value = if Path::new(&output_path).exists() {
        let content = fs::read_to_string(&output_path)?;
        serde_json::from_str(&content)?
    } else {
        json!({ "eco": eco, "months": {} })
    };

    // Skip months that are already present in the file.
    if !consolidated["months"][month].is_null() {
        println!("Skipping {} {} (already present)", eco, month);
        return Ok(());
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

    consolidated["months"][month] = month_data;

    // Atomic write: write to .tmp then rename to avoid corruption on crash.
    if let Some(parent) = Path::new(&tmp_path).parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&tmp_path, serde_json::to_string_pretty(&consolidated)?)?;
    fs::rename(&tmp_path, &output_path)?;

    println!("Fetched {} {}", eco, month);

    tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;

    Ok(())
}