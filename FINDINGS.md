# OpenCast Findings

*Last updated: 2026-04-30 06:15 UTC*

---

## Summary

Across the 20 tracked openings, **Queen's Gambit (D06)** shows the largest positive delta (+0.0303), meaning humans at 2000-rated blitz outperform Stockfish's win-probability prediction by the widest margin. At the other extreme, **Grunfeld Defense (D70)** has the largest negative delta (-0.0644), indicating it is the most frequently misplayed or theory-dependent opening in the dataset. The steepest ARIMA forecast trend belongs to **Pirc Defense (B07)**, whose win rate is projected to be falling most sharply over the next three months.

---

## Per-Opening Analysis

### D06 — Queen's Gambit

The +0.0303 engine-human delta suggests that 2000-rated blitz players slightly outperform engines in the Queen's Gambit opening, but only marginally, implying that they are able to capitalize on nuances in the position that engines miss. The stable ARIMA win-rate trend indicates that this overperformance is consistent across games, suggesting that human players have developed a reliable approach to handling the Queen's Gambit that engine analysis has not yet fully grasped.
### C60 — Ruy Lopez

The Ruy Lopez opening (C60) is handled similarly to engine expectations by 2000-rated blitz players, with a +0.0190 engine-human delta indicating no significant deviation from optimal play. The rising ARIMA win-rate trend suggests that human players are improving their performance against the Ruy Lopez, potentially due to increased familiarity and adaptation to engine-like strategies.
### A10 — English Opening

The English Opening (A10) is handled by 2000-rated blitz players in a manner that is negligibly better than what engines evaluate, with a delta of +0.0171, indicating that humans slightly outperform engines in this opening. The stable ARIMA win-rate trend suggests that this outperformance is consistent and not due to a one-time anomaly, implying that humans may have a subtle edge in this opening that engines are not fully capturing.
### A45 — Trompowsky Attack

The data suggests that 2000-rated blitz players perform slightly worse than expected when employing the Trompowsky Attack, as evidenced by the -0.0014 engine-human delta, indicating a marginal disadvantage. The falling ARIMA win-rate trend further implies that players' results have been trending downward over time, suggesting that the opening may be more vulnerable than anticipated at the 2000-rated level.
### C50 — Italian Game

The Italian Game (C50) shows a slight deviation from engine expectations, with 2000-rated blitz players performing -0.0033 delta, indicating that engines are slightly more favorable to this opening. The stable ARIMA win-rate trend suggests that this deviation is consistent and not a short-term anomaly, implying that human players are effectively countering engine play in the Italian Game.
### D00 — London System

The London System (D00) reveals a slight, but consistent, underperformance by 2000-rated blitz players compared to engine expectations, as evidenced by the -0.0062 engine-human delta. The falling ARIMA win-rate trend suggests that this underperformance is a persistent trend, with players struggling to capitalize on the opening's theoretical advantages against engines.
### D30 — Queen's Gambit Declined

The Queen's Gambit Declined (D30) opening results in a consistent engine-human delta of -0.0107, indicating that 2000-rated blitz players generally adhere to engine-suggested moves and avoid deviating from the optimal path. The stable ARIMA win-rate trend suggests that this adherence to engine-suggested moves is a successful strategy for these players, as their win rates remain steady against the Queen's Gambit Declined.
### C44 — King's Pawn Game

The King's Pawn Game (C44) shows a slight engine disadvantage for 2000-rated blitz players, with a delta of -0.0227, indicating that engines are favored over humans in this opening. However, the stable ARIMA win-rate trend suggests that human performance is consistently outperforming engine expectations, indicating a potential edge for human players in this opening at the 2000 rating level.
### C41 — Philidor Defense

The Philidor Defense (C41) shows a consistent engine-human delta of -0.0252, indicating that 2000-rated blitz players slightly underperform against engine expectations, suggesting a potential for improvement in their understanding of the opening. The stable ARIMA win-rate trend further implies that players' results against the Philidor Defense have been steady over time, with no significant deviations from the expected level of performance.
### E20 — Nimzo-Indian Defense

The Nimzo-Indian Defense (E20) has an engine-human delta of -0.0281, indicating that 2000-rated blitz players slightly underperform compared to engine expectation, but the gap is consistent with engine evaluation. The falling ARIMA win-rate trend suggests that as the opening progresses, human players' performance advantage over engines tends to diminish, contradicting the initial slight underperformance.
### A00 — Polish Opening

The Polish Opening (A00) presents a slight disadvantage to 2000-rated blitz players, as indicated by a delta of -0.0281, suggesting their play deviates from engine evaluation expectations. The falling ARIMA win-rate trend suggests that, despite their consistent deviation from engine play, human performance does not improve over time, implying a persistent difficulty in handling this opening.
### B12 — Caro-Kann Defense

The Caro-Kann Defense (B12) exhibits a moderate engine-human delta of -0.0388, indicating that 2000-rated blitz players slightly underperform compared to engine expectations. The stable ARIMA win-rate trend suggests that this underperformance is consistent and not a result of a fluctuating trend, implying a persistent gap in playing strength between human and engine play in this opening.
### C00 — French Defense

The French Defense (C00) is a heavily theory-driven opening where human players, particularly those rated 2000 in blitz games, underperform compared to engine recommendations, with a delta of -0.0423 indicating a significant gap. Notably, the ARIMA win-rate trend is stable, suggesting that human players' performance in the French Defense is consistent in terms of results, but consistently lags behind engine expectations.
### B20 — Sicilian Defense

The Sicilian Defense (B20) is a theory-heavy opening that 2000-rated blitz players often misplay, favoring engine strategies by a margin of -0.0447. Despite this, the win-rate trend for this opening is stable, suggesting that players' mistakes are consistently countered by their opponents' predictable responses.
### C20 — King's Gambit

The King's Gambit opening shows a significant engine-human delta of -0.0465, indicating that 2000-rated blitz players frequently struggle to execute this opening, often deviating from optimal lines. Meanwhile, the rising ARIMA win-rate trend suggests that while humans may not be able to fully match engine play, their understanding and execution of the King's Gambit is gradually improving.
### E60 — King's Indian Defense

The King's Indian Defense (E60) appears to be a misplayed or theory-heavy opening for 2000-rated blitz players, as indicated by the engine-human delta of -0.0501, suggesting a systematic disadvantage. The stable ARIMA win-rate trend suggests that this disadvantage is consistent and not just a short-term anomaly, implying that the opening remains challenging for human players to navigate effectively.
### B06 — Modern Defense

The Modern Defense (B06) is an engine-favoured opening, with a delta of -0.0526 indicating that human players, particularly those at the 2000 rating level, frequently make mistakes or fall behind in theoretical understanding, leading to a loss. Despite this, the ARIMA win-rate trend remains stable, suggesting that the opening's unpredictable nature may counterbalance the engine's advantage, making it a viable choice for players who can adapt to the dynamic position.
### B07 — Pirc Defense

The Pirc Defense (B07) is a theory-heavy opening that is frequently misplayed by 2000-rated blitz players, resulting in a -0.0558 engine-human delta, indicating a significant disadvantage when facing engine play. The falling ARIMA win-rate trend suggests that the delta is not an isolated issue, but rather a systemic problem, implying that players struggle to effectively play this opening against engines consistently.
### B01 — Scandinavian Defense

The Scandinavian Defense shows a consistently stable win-rate trend among 2000-rated blitz players, indicating that while engines favor this opening, human players are able to adapt and perform at a similar level. The engine-human delta of -0.0581 suggests that humans are frequently overestimating the risks of this opening, allowing engines to gain an edge due to theory-heavy play.
### D70 — Grunfeld Defense

The Grunfeld Defense (D70) reveals a significant engine-human delta, indicating that 2000-rated blitz players tend to favor strategies that engines deem inferior, often resulting in a 6.44% disadvantage. Furthermore, the falling ARIMA win-rate trend suggests that despite efforts to improve, human players continue to struggle with the Grunfeld, failing to capitalize on engine-disfavored strategies effectively.

---

*Generated with Ollama (llama3.1:latest).*
