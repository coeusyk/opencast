use reqwest::Client;
use std::fs;
use std::path::Path;
use crate::models::OpeningStats;

pub async fn fetch_opening_month(
    client: &Client,
    moves: &str,
    month: &str,
    rating: u32,
    speed: &str,
    eco: &str,
) -> Result<(), Box<dyn std::error::Error>> {
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

    let stats: OpeningStats = response.json().await?;
    let output_path = format!("../data/raw/{}_{}.json", eco, month);

    if let Some(parent) = Path::new(&output_path).parent() {
        fs::create_dir_all(parent)?;
    }

    fs::write(&output_path, serde_json::to_string_pretty(&stats)?)?;
    println!("Fetched {} {}", eco, month);

    tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;

    Ok(())
}