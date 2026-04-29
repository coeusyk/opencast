use serde::{Deserialize, Serialize};

#[derive(Deserialize, Serialize, Debug)]
pub struct OpeningStats {
    pub white: u64,
    pub draws: u64,
    pub black: u64,
    pub moves: Vec<MoveStats>,
}

#[derive(Deserialize, Serialize, Debug)]
pub struct MoveStats {
    pub uci: String,
    pub san: String,
    pub white: u64,
    pub black: u64,
    pub draws: u64,
}