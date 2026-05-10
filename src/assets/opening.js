let openingsDataCache = null;
let openingLinesCache = null;

const THEME = window.__OPENCAST_THEME__ || {};
const ECO_COLORS = THEME.ecoColors || {};
const PANEL_BG = THEME.panelBg || "#0e0e0f";
const GRID_COLOR = THEME.gridColor || "rgba(255, 255, 255, 0.06)";
const TEXT_PRIMARY = THEME.textPrimary || "#ededee";
const TEXT_SECONDARY = THEME.textSecondary || "#8b8b8f";
const BODY_FONT = THEME.bodyFont || "'Inter', system-ui, sans-serif";
const FALLBACK_NARRATIVE = window.__OPENCAST_FALLBACK_NARRATIVE__ || "No analysis available yet.";
const TIER_TOOLTIP = "T1: >=1000 avg monthly games + >=24 months -> model-selected forecast + engine evaluation\nT2: 400-999 avg monthly games -> model-selected trend, no engine delta\nT3: <400 avg monthly games -> descriptive stats only";

function safeText(tag, text, attrs) {
	const el = document.createElement(tag);
	el.textContent = text == null ? "" : String(text);
	if (attrs) {
		Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
	}
	return el;
}

function setStyle(el, cssText) {
	el.style.cssText = cssText;
	return el;
}

function clearNode(el) {
	el.replaceChildren();
	return el;
}

function syncBackLink() {
	const backLink = document.getElementById("back-to-openings");
	try {
		const ref = document.referrer || "";
		if (ref.includes("openings.html#")) {
			const refHash = ref.split("#")[1] || "";
			if (refHash) {
				backLink.href = "openings.html#" + refHash;
				return;
			}
		}
	} catch (_) {}
	const params = new URLSearchParams(window.location.search);
	const back = params.get("back");
	if (back) {
		backLink.href = "openings.html#" + back;
	}
}

function hexToRgba(hexColor, alpha) {
	const h = String(hexColor || "").replace("#", "");
	const r = parseInt(h.slice(0, 2), 16);
	const g = parseInt(h.slice(2, 4), 16);
	const b = parseInt(h.slice(4, 6), 16);
	return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function computeOlsTrend(actuals) {
	if (!Array.isArray(actuals) || actuals.length < 3) return null;
	const points = actuals
		.map((d) => {
			const t = Date.parse(`${d.month}-01T00:00:00Z`);
			const y = Number(d.win_rate);
			return Number.isFinite(t) && Number.isFinite(y) ? { x: t, y } : null;
		})
		.filter(Boolean);
	if (points.length < 3) return null;
	const n = points.length;
	const xMean = points.reduce((sum, p) => sum + p.x, 0) / n;
	const yMean = points.reduce((sum, p) => sum + p.y, 0) / n;
	let numerator = 0;
	let denominator = 0;
	for (const p of points) {
		const dx = p.x - xMean;
		numerator += dx * (p.y - yMean);
		denominator += dx * dx;
	}
	if (denominator === 0) return null;
	const slopePerMs = numerator / denominator;
	const intercept = yMean - slopePerMs * xMean;
	const trendY = actuals.map((d) => {
		const t = Date.parse(`${d.month}-01T00:00:00Z`);
		return Number.isFinite(t) ? slopePerMs * t + intercept : null;
	});
	const msPerMonth = 30.4375 * 24 * 60 * 60 * 1000;
	const slopePerMonth = slopePerMs * msPerMonth;
	const slopeThreshold = 0.0003;
	const direction = Math.abs(slopePerMonth) < slopeThreshold ? "stable" : slopePerMonth > 0 ? "rising" : "falling";
	return { trendY, slopePerMonth, direction };
}

async function loadOpeningsData() {
	if (openingsDataCache) return openingsDataCache;
	const response = await fetch("assets/openings_data.json", { cache: "no-store" });
	if (!response.ok) throw new Error(`Failed to load openings_data.json (${response.status})`);
	openingsDataCache = await response.json();
	return openingsDataCache;
}

async function loadOpeningLines() {
	if (openingLinesCache) return openingLinesCache;
	try {
		const response = await fetch("assets/opening_lines.json", { cache: "no-store" });
		if (!response.ok) {
			openingLinesCache = {};
			return openingLinesCache;
		}
		openingLinesCache = await response.json();
	} catch (_) {
		openingLinesCache = {};
	}
	return openingLinesCache;
}

function resolveEco(data) {
	const ecos = Object.keys(data);
	if (!ecos.length) return null;
	const requested = new URLSearchParams(window.location.search).get("eco");
	if (requested && data[requested]) return requested;
	return ecos[0];
}

function appendStatCard(parent, label, value, valueStyle) {
	const card = document.createElement("div");
	card.className = "historical-stat";
	const labelEl = safeText("p", label);
	labelEl.className = "historical-label";
	const valueEl = safeText("p", value);
	valueEl.className = "historical-value";
	if (valueStyle) valueEl.style.cssText = valueStyle;
	card.append(labelEl, valueEl);
	parent.appendChild(card);
	return card;
}

function renderOpeningBoard(eco, openingLines) {
	const boardSection = document.getElementById("opening-board-section");
	const frameEl = document.querySelector(".opening-board-frame");
	const boardEl = document.getElementById("opening-board");
	const ranksEl = document.getElementById("opening-board-ranks");
	const filesEl = document.getElementById("opening-board-files");
	const moveListEl = document.getElementById("opening-move-list");
	const lineNameEl = document.getElementById("opening-line-name");
	const flipBtn = document.getElementById("btn-flip");
	const resetBtn = document.getElementById("btn-reset");
	const prevBtn = document.getElementById("btn-prev");
	const nextBtn = document.getElementById("btn-next");
	const lines = openingLines && openingLines[eco] && Array.isArray(openingLines[eco].lines) ? openingLines[eco].lines : [];
	const primaryLine = lines.find((line) => line.id === "main") || lines[0];
	if (!primaryLine || !Array.isArray(primaryLine.moves_san) || !primaryLine.moves_san.length) {
		boardSection.style.display = "none";
		if (window.__opencastBoardKeyHandler) {
			document.removeEventListener("keydown", window.__opencastBoardKeyHandler);
			window.__opencastBoardKeyHandler = null;
		}
		return;
	}
	if (typeof Chess === "undefined" || typeof Chessboard === "undefined") {
		boardSection.style.display = "none";
		return;
	}
	const startingFen = primaryLine.starting_fen && primaryLine.starting_fen !== "startpos" ? primaryLine.starting_fen : null;
	const seedGame = new Chess();
	if (startingFen && !seedGame.load(startingFen)) {
		boardSection.style.display = "none";
		return;
	}
	const initialFen = seedGame.fen();
	const moves = primaryLine.moves_san.slice(0, 12);
	const board = Chessboard(boardEl, { position: initialFen, draggable: false, showNotation: false, pieceTheme: "assets/chesspieces/wikipedia/{piece}.png" });
	let currentIndex = 0;
	let boardFlipped = false;
	function renderCoordinates(isFlipped) {
		const rankLabels = isFlipped ? ["1", "2", "3", "4", "5", "6", "7", "8"] : ["8", "7", "6", "5", "4", "3", "2", "1"];
		const fileLabels = isFlipped ? ["h", "g", "f", "e", "d", "c", "b", "a"] : ["a", "b", "c", "d", "e", "f", "g", "h"];
		ranksEl.innerHTML = rankLabels.map((label) => `<span class="board-coord">${label}</span>`).join("");
		filesEl.innerHTML = fileLabels.map((label) => `<span class="board-coord">${label}</span>`).join("");
	}
	function syncCoordinateGeometry() {
		const boardGrid = boardEl.querySelector(".board-b72b1");
		const boardRect = boardGrid ? boardGrid.getBoundingClientRect() : boardEl.getBoundingClientRect();
		const boardPx = Math.round(boardRect.width);
		if (!Number.isFinite(boardPx) || boardPx <= 0) return;
		frameEl.style.gridTemplateColumns = `1rem ${boardPx}px`;
		frameEl.style.gridTemplateRows = `${boardPx}px 1rem`;
		boardEl.style.width = `${boardPx}px`;
		boardEl.style.height = `${boardPx}px`;
	}
	function renderMoveList(activeIndex) {
		clearNode(moveListEl);
		for (let i = 0; i < moves.length; i += 2) {
			const moveNo = Math.floor(i / 2) + 1;
			const row = safeText("div", "");
			row.className = "move-row";
			const moveNumber = safeText("span", `${moveNo}.`);
			moveNumber.className = "move-number";
			const white = safeText("span", moves[i] || "");
			white.className = "move-token";
			if (i < activeIndex) white.classList.add("played");
			if (i === activeIndex - 1) white.classList.add("active");
			row.append(moveNumber, white);
			const blackIndex = i + 1;
			if (blackIndex < moves.length) {
				const black = safeText("span", moves[blackIndex] || "");
				black.className = "move-token";
				if (blackIndex < activeIndex) black.classList.add("played");
				if (blackIndex === activeIndex - 1) black.classList.add("active");
				row.appendChild(black);
			}
			moveListEl.appendChild(row);
		}
	}
	function goToMove(targetIndex) {
		const clamped = Math.max(0, Math.min(targetIndex, moves.length));
		const game = new Chess();
		game.load(initialFen);
		for (let i = 0; i < clamped; i++) {
			const next = game.move(moves[i], { sloppy: true });
			if (!next) break;
		}
		boardEl.style.opacity = "0.7";
		board.position(game.fen(), true);
		boardEl.style.opacity = "1";
		currentIndex = clamped;
		renderMoveList(currentIndex);
		prevBtn.disabled = currentIndex <= 0;
		nextBtn.disabled = currentIndex >= moves.length;
	}
	lineNameEl.textContent = primaryLine.name || `Main line (${eco})`;
	boardSection.style.display = "block";
	renderCoordinates(boardFlipped);
	flipBtn.onclick = () => {
		boardFlipped = !boardFlipped;
		board.orientation(boardFlipped ? "black" : "white");
		syncCoordinateGeometry();
		renderCoordinates(boardFlipped);
	};
	resetBtn.onclick = () => goToMove(0);
	prevBtn.onclick = () => goToMove(currentIndex - 1);
	nextBtn.onclick = () => goToMove(currentIndex + 1);
	if (window.__opencastBoardKeyHandler) document.removeEventListener("keydown", window.__opencastBoardKeyHandler);
	window.__opencastBoardKeyHandler = (event) => {
		if (event.key === "ArrowRight") nextBtn.click();
		if (event.key === "ArrowLeft") prevBtn.click();
	};
	document.addEventListener("keydown", window.__opencastBoardKeyHandler);
	goToMove(0);
	const forceBoardResize = () => {
		board.resize();
		syncCoordinateGeometry();
		goToMove(currentIndex);
	};
	requestAnimationFrame(forceBoardResize);
	setTimeout(forceBoardResize, 80);
}

function renderHistoricalSummary(data) {
	const historicalSummaryBox = document.getElementById("historical-summary-box");
	const actuals = Array.isArray(data.actuals) ? data.actuals : [];
	const vals = actuals.map((d) => Number(d.win_rate)).filter((v) => Number.isFinite(v));
	if (vals.length < 3) {
		historicalSummaryBox.style.display = "none";
		clearNode(historicalSummaryBox);
		return;
	}
	const last3 = vals.slice(-3);
	const last12 = vals.slice(-12);
	const avg3 = last3.reduce((a, b) => a + b, 0) / last3.length;
	const avg12 = last12.reduce((a, b) => a + b, 0) / last12.length;
	const above50 = vals.filter((v) => v > 0.5).length;
	const fmt = (v) => `${(v * 100).toFixed(2)}%`;
	clearNode(historicalSummaryBox);
	historicalSummaryBox.style.display = "block";
	historicalSummaryBox.appendChild(setStyle(safeText("h3", "Historical Summary"), "margin:0 0 0.85rem;"));
	const grid = safeText("div", "");
	grid.className = "historical-grid";
	appendStatCard(grid, "3-Month Avg", fmt(avg3));
	appendStatCard(grid, "12-Month Avg", fmt(avg12));
	appendStatCard(grid, "Months Above 50%", `${above50} / ${vals.length} months`);
	historicalSummaryBox.appendChild(grid);
	historicalSummaryBox.appendChild(setStyle(safeText("p", `Based on ${vals.length} months of data.`), `margin:0.6rem 0 0;font-size:0.78rem;color:${TEXT_SECONDARY};`));
}

function renderForecastStats(data) {
	const forecastStatsBox = document.getElementById("forecast-stats-box");
	if (Number(data.model_tier) === 3) {
		forecastStatsBox.style.display = "none";
		clearNode(forecastStatsBox);
		return;
	}
	const slope = Number(data.trend_slope_per_month);
	const r2 = Number(data.trend_r_squared);
	const streak = Number(data.trend_streak_months);
	const conf = String(data.trend_confidence || "low").toLowerCase();
	const slopeTxt = Number.isFinite(slope) ? `${slope >= 0 ? "+" : ""}${(slope * 100).toFixed(4)} pp/month` : "—";
	const confColor = conf === "high" ? "#7BE495" : conf === "medium" ? "#F6C177" : TEXT_SECONDARY;
	clearNode(forecastStatsBox);
	forecastStatsBox.style.display = "block";
	forecastStatsBox.appendChild(setStyle(safeText("h3", "Trend Signal"), "margin:0 0 0.85rem;"));
	const wrap = safeText("div", "");
	setStyle(wrap, "display:flex;flex-wrap:wrap;gap:0.6rem;");
	for (const [label, value] of [["Slope", slopeTxt], ["R²", Number.isFinite(r2) ? r2.toFixed(3) : "—"], ["Sustained", Number.isFinite(streak) ? `${streak} months` : "—"], ["Confidence", conf]]) {
		const chip = safeText("div", "");
		chip.className = "stat-chip";
		if (label === "Confidence") chip.style.borderColor = confColor;
		const labelEl = safeText("span", label);
		labelEl.className = "chip-label";
		const valueEl = safeText("span", value);
		valueEl.className = "chip-value";
		if (label === "Confidence") valueEl.style.color = confColor;
		chip.append(labelEl, valueEl);
		wrap.appendChild(chip);
	}
	forecastStatsBox.appendChild(wrap);
}

function renderStructuralBreaks(data) {
	const breaksBox = document.getElementById("breaks-box");
	const breaks = Array.isArray(data.structural_breaks) ? data.structural_breaks : [];
	if (!breaks.length) {
		breaksBox.style.display = "none";
		clearNode(breaksBox);
		return;
	}
	clearNode(breaksBox);
	breaksBox.style.display = "block";
	breaksBox.appendChild(setStyle(safeText("h3", "Structural Breaks Detected"), "margin:0 0 0.5rem;"));
	breaksBox.appendChild(setStyle(safeText("p", "Statistical regime changes (Chow test) detected at:"), `margin:0 0 0.6rem;font-size:0.82rem;color:${TEXT_SECONDARY};`));
	const wrap = safeText("div", "");
	setStyle(wrap, "display:flex;gap:0.5rem;flex-wrap:wrap;");
	for (const brk of breaks) wrap.appendChild(setStyle(safeText("span", brk), "padding:0.2em 0.65em;background:rgba(246,193,119,0.12);border:1px solid rgba(246,193,119,0.25);border-radius:4px;color:#F6C177;font-size:0.8rem;"));
	breaksBox.appendChild(wrap);
	breaksBox.appendChild(setStyle(safeText("p", "Win-rate behaviour may differ significantly before and after these dates."), `margin:0.6rem 0 0;font-size:0.78rem;color:${TEXT_SECONDARY};opacity:0.7;`));
}

function renderLinesDrivingTrend(data) {
	const box = document.getElementById("lines-box");
	const lines = Array.isArray(data.lines_driving_trend) ? data.lines_driving_trend : [];
	const MIN_LINE_GAMES = 5;
	const MIN_LINE_SHARE = 0.005;
	if (!lines.length) {
		box.style.display = "none";
		clearNode(box);
		return;
	}
	const fmtPct = (v) => (v != null ? (v * 100).toFixed(2) + "%" : "—");
	const fmtPp = (v) => { if (v == null) return "—"; const pp = (v * 100).toFixed(2); return (v >= 0 ? "+" : "") + pp + "%"; };
	clearNode(box);
	box.style.display = "block";
	box.appendChild(safeText("h3", "Lines Driving The Trend"));
	const asOf = lines[0] && lines[0].month ? `Top move choices by volume and 12-month win-rate movement. As of ${lines[0].month}.` : "Top move choices by volume and 12-month win-rate movement. Latest month.";
	box.appendChild(setStyle(safeText("p", asOf), `margin:0.25rem 0 0.8rem;color:${TEXT_SECONDARY};font-size:0.8rem;`));
	const table = document.createElement("table");
	setStyle(table, "width:100%;border-collapse:collapse;font-size:0.84rem;");
	table.innerHTML = `<thead><tr style="color:${TEXT_SECONDARY};font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;"><th style="text-align:left;padding:0 0.6rem 0.35rem 0;">Move</th><th style="text-align:right;padding:0 0.6rem 0.35rem;">Share</th><th style="text-align:right;padding:0 0.6rem 0.35rem;">Win Rate</th><th style="text-align:right;padding:0 0.6rem 0.35rem;">Win rate shift (12m)</th></tr></thead><tbody></tbody>`;
	const tbody = table.querySelector("tbody");
	for (const r of lines.slice(0, 3)) {
		const reliable = Number(r.games) >= MIN_LINE_GAMES && Number(r.share_of_games) >= MIN_LINE_SHARE;
		const shiftText = reliable ? fmtPp(r.delta_wr_12m) : "—";
		const shiftColor = !reliable || r.delta_wr_12m == null ? TEXT_SECONDARY : r.delta_wr_12m >= 0 ? "#7BE495" : "#F28DA6";
		const tr = document.createElement("tr");
		const moveCell = document.createElement("td");
		moveCell.style.cssText = "padding:0.45rem 0.6rem 0.45rem 0;";
		const san = safeText("strong", r.san || "—");
		san.style.color = TEXT_PRIMARY;
		moveCell.append(san, setStyle(safeText("div", r.uci || ""), `font-size:0.74rem;color:${TEXT_SECONDARY};`));
		tr.append(moveCell, setStyle(safeText("td", fmtPct(r.share_of_games)), "padding:0.45rem 0.6rem;text-align:right;"), setStyle(safeText("td", fmtPct(r.white_win_rate)), "padding:0.45rem 0.6rem;text-align:right;"), setStyle(safeText("td", shiftText), `padding:0.45rem 0.6rem;text-align:right;color:${shiftColor};`));
		tbody.appendChild(tr);
	}
	box.appendChild(table);
}

function buildTierLegendTable() {
	const table = document.createElement("table");
	table.style.cssText = `border-collapse:collapse;font-size:0.825rem;color:${TEXT_SECONDARY};`;
	const tbody = document.createElement("tbody");
	for (const [tier, desc, cls] of [["T1", "≥ 1 000 avg monthly games + ≥ 24 months of data — model-selected forecasting & engine evaluation", "tier-badge-1"], ["T2", "400 – 999 avg monthly games — model-selected trend estimation, no engine delta", "tier-badge-2"], ["T3", "< 400 avg monthly games — descriptive stats only, insufficient volume for modelling", "tier-badge-3"]]) {
		const tr = document.createElement("tr");
		const left = document.createElement("td");
		left.style.cssText = "padding:0.3rem 1.2rem 0.3rem 0;white-space:nowrap;";
		const badge = safeText("span", tier);
		badge.className = `tier-badge ${cls}`;
		left.appendChild(badge);
		tr.append(left, setStyle(safeText("td", desc), "padding:0.3rem 0;"));
		tbody.appendChild(tr);
	}
	table.appendChild(tbody);
	return table;
}

function appendStatsRow(tbody, label, value, color) {
	const tr = document.createElement("tr");
	const left = setStyle(safeText("td", label), `padding:0.4rem 1rem 0.4rem 0;color:${TEXT_SECONDARY};`);
	const right = setStyle(safeText("td", value), "padding:0.4rem 0;");
	if (color) right.style.color = color;
	tr.append(left, right);
	tbody.appendChild(tr);
}

function renderMissingState(chartEl) {
	clearNode(chartEl);
	chartEl.style.display = "block";
	const wrapper = document.createElement("div");
	wrapper.style.cssText = `margin-top:2rem;padding:1.5rem 2rem;border:1px solid ${GRID_COLOR};border-radius:8px;`;
	wrapper.appendChild(setStyle(safeText("p", "No game data available for this opening."), `margin:0 0 0.75rem;font-size:1rem;font-weight:600;color:${TEXT_PRIMARY};`));
	const explain = document.createElement("p");
	explain.style.cssText = `margin:0 0 1rem;font-size:0.875rem;color:${TEXT_SECONDARY};`;
	explain.append(document.createTextNode("This opening is classified as "), setStyle(safeText("strong", "Tier 3"), `color:${TEXT_PRIMARY};`), document.createTextNode(" — it exists in the ECO catalog but doesn't meet the minimum volume threshold for analysis."));
	wrapper.append(explain, buildTierLegendTable(), setStyle(safeText("p", "Data will appear here automatically once this opening meets the volume threshold."), `margin:1rem 0 0;font-size:0.8rem;color:${TEXT_SECONDARY};opacity:0.7;`));
	chartEl.appendChild(wrapper);
}

function renderDescriptiveState(chartEl, opening, titleText, warningText) {
	const fmtPct = (v) => (v != null ? (v * 100).toFixed(2) + "%" : "—");
	const fmt2 = (v) => (v != null ? (v * 100).toFixed(2) : "—");
	const trend = opening.trend_direction || "flat";
	const trendArrow = trend === "up" ? "↑" : trend === "down" ? "↓" : "→";
	const trendColor = trend === "up" ? "#7BE495" : trend === "down" ? "#F28DA6" : TEXT_SECONDARY;
	clearNode(chartEl);
	chartEl.style.display = "block";
	if (warningText) chartEl.appendChild(setStyle(safeText("div", warningText), "margin-top:1rem;padding:0.75rem 1rem;border-left:3px solid #F28DA6;background:rgba(242,141,166,0.08);border-radius:4px;margin-bottom:1.5rem;font-size:0.85rem;color:#F28DA6;"));
	const wrapper = safeText("div", "");
	wrapper.className = "tier3-stats";
	if (!warningText) wrapper.style.marginTop = "1.5rem";
	wrapper.appendChild(setStyle(safeText("h2", titleText), `font-size:1rem;font-weight:600;margin-bottom:1rem;color:${TEXT_SECONDARY};`));
	const table = document.createElement("table");
	table.style.cssText = "border-collapse:collapse;width:100%;max-width:540px;";
	const tbody = document.createElement("tbody");
	appendStatsRow(tbody, "Last month", opening.last_month || "—");
	appendStatsRow(tbody, "Last win rate", fmtPct(opening.last_win_rate));
	appendStatsRow(tbody, "Mean win rate", fmtPct(opening.mean_win_rate));
	appendStatsRow(tbody, "Std dev", fmt2(opening.std_win_rate) + "%");
	appendStatsRow(tbody, "3-month MA", fmtPct(opening.ma3));
	appendStatsRow(tbody, "Trend", `${trendArrow} ${trend}`, trendColor);
	appendStatsRow(tbody, "Months of data", opening.months_available ?? "—");
	table.appendChild(tbody);
	wrapper.appendChild(table);
	chartEl.appendChild(wrapper);
}

function renderOpening(eco, opening, openingLines) {
	const name = opening.name || eco;
	document.getElementById("opening-title").textContent = `${name} (${eco})`;
	document.title = `${eco} — ${name} | OpenCast`;
	const tier = opening.model_tier;
	const tierBadge = document.getElementById("opening-tier-badge");
	const modelBadge = document.getElementById("opening-model-badge");
	const qualityBadge = document.getElementById("opening-forecast-quality-badge");
	if (tier) {
		tierBadge.className = `tier-badge tier-badge-${tier}`;
		tierBadge.textContent = `T${tier}`;
		tierBadge.title = TIER_TOOLTIP;
	} else {
		tierBadge.className = "";
		tierBadge.textContent = "";
	}
	const modelName = String(opening.model_name || "").trim();
	if (modelName && tier !== 3) {
		modelBadge.className = "meta-badge";
		modelBadge.textContent = `Model: ${modelName.replaceAll("_", "-")}`;
	} else {
		modelBadge.className = "";
		modelBadge.textContent = "";
	}
	const quality = String(opening.forecast_quality || "").toLowerCase();
	if (quality && tier !== 3) {
		qualityBadge.className = `meta-badge quality-${quality}`;
		qualityBadge.textContent = `Forecast confidence: ${quality}`;
	} else {
		qualityBadge.className = "";
		qualityBadge.textContent = "";
	}
	const narrativeBox = document.getElementById("opening-narrative");
	const narrative = opening.narrative || FALLBACK_NARRATIVE;
	if (!narrative || narrative === FALLBACK_NARRATIVE || !String(narrative).trim()) {
		narrativeBox.style.display = "none";
	} else {
		narrativeBox.style.display = "";
		const narrativeEl = document.querySelector("#opening-narrative p");
		narrativeEl.textContent = narrative;
		narrativeEl.style.color = TEXT_PRIMARY;
	}
	renderOpeningBoard(eco, openingLines);
	renderHistoricalSummary(opening);
	renderForecastStats(opening);
	renderStructuralBreaks(opening);
	renderLinesDrivingTrend(opening);
	const chartEl = document.getElementById("opening-chart");
	const engineBox = document.getElementById("engine-box");
	if (opening.data_status === "missing") {
		engineBox.style.display = "none";
		engineBox.innerHTML = "";
		document.getElementById("lines-box").style.display = "none";
		document.getElementById("forecast-stats-box").style.display = "none";
		document.getElementById("breaks-box").style.display = "none";
		document.getElementById("historical-summary-box").style.display = "none";
		narrativeBox.style.display = "none";
		renderMissingState(chartEl);
		return;
	}
	if (opening.data_status === "sparse") {
		engineBox.style.display = "none";
		engineBox.innerHTML = "";
		document.getElementById("forecast-stats-box").style.display = "none";
		document.getElementById("breaks-box").style.display = "none";
		renderDescriptiveState(chartEl, opening, "Descriptive Statistics (sparse — insufficient data for modelling)", `Limited data (${opening.months_available ?? 0} months) — results may be unreliable.`);
		return;
	}
	if (opening.model_tier === 3) {
		engineBox.style.display = "none";
		engineBox.innerHTML = "";
		document.getElementById("forecast-stats-box").style.display = "none";
		document.getElementById("breaks-box").style.display = "none";
		renderDescriptiveState(chartEl, opening, "Descriptive Statistics (Tier 3 — insufficient data for modelling)", "");
		return;
	}
	const color = ECO_COLORS[(opening.eco_group || eco.charAt(0) || "").toUpperCase()] || THEME.accent || "#57C7FF";
	const actuals = opening.actuals || [];
	const forecasts = opening.forecast || [];
	const qualityLower = String(opening.forecast_quality || "").toLowerCase();
	const lowForecastQuality = qualityLower === "low";
	const traces = [{ x: actuals.map((d) => d.month), y: actuals.map((d) => d.win_rate), mode: "lines", name: "Actual", line: { color, width: 2 }, type: "scatter" }];
	if (forecasts.length) {
		traces.push({ x: forecasts.map((d) => d.month), y: forecasts.map((d) => d.value), mode: "lines", name: "Forecast", line: { color, width: 1.5, dash: "dash" }, opacity: lowForecastQuality ? 0.46 : 0.95, type: "scatter" });
		traces.push({ x: forecasts.map((d) => d.month).concat(forecasts.map((d) => d.month).slice().reverse()), y: forecasts.map((d) => d.upper).concat(forecasts.map((d) => d.lower).slice().reverse()), fill: "toself", fillcolor: hexToRgba(color, lowForecastQuality ? 0.07 : 0.12), line: { color: "rgba(0,0,0,0)" }, showlegend: false, name: "95% CI", type: "scatter" });
	}
	const olsTrend = computeOlsTrend(actuals);
	const trendConfidence = String(opening.trend_confidence || "low").toLowerCase();
	if (olsTrend) {
		const trendDirection = String(opening.trend_direction || olsTrend.direction || "stable").toLowerCase();
		const trendColor = trendDirection === "rising" ? "#7BE495" : trendDirection === "falling" ? "#F28DA6" : TEXT_SECONDARY;
		traces.push({ x: actuals.map((d) => d.month), y: olsTrend.trendY, mode: "lines", name: `Trend (${trendDirection})`, line: { color: trendColor, width: 1.5, dash: "longdash" }, opacity: trendConfidence === "high" ? 0.78 : trendConfidence === "medium" ? 0.55 : 0.30, type: "scatter" });
	}
	const isNarrow = window.matchMedia("(max-width: 760px)").matches;
	Plotly.newPlot("opening-chart", traces, { xaxis: { title: isNarrow ? "" : "Month", gridcolor: GRID_COLOR, zerolinecolor: GRID_COLOR, tickfont: { color: TEXT_SECONDARY, size: isNarrow ? 10 : 12 }, tickangle: isNarrow ? -35 : 0 }, yaxis: { title: isNarrow ? "" : "Win Rate", gridcolor: GRID_COLOR, zerolinecolor: GRID_COLOR, tickfont: { color: TEXT_SECONDARY, size: isNarrow ? 10 : 12 } }, plot_bgcolor: PANEL_BG, paper_bgcolor: PANEL_BG, font: { family: BODY_FONT, color: TEXT_PRIMARY }, margin: isNarrow ? { t: 36, r: 8, b: 52, l: 40 } : { t: 36, r: 20, b: 52, l: 56 }, legend: { orientation: "h", x: 0, y: 1.0, xanchor: "left", yanchor: "bottom", font: { size: 11, color: TEXT_SECONDARY }, bgcolor: "rgba(0,0,0,0)", borderwidth: 0, itemwidth: 30 } }, { responsive: true });
	const hasEngine = opening.engine_cp !== null && opening.p_engine !== null && opening.human_win_rate !== null && opening.delta !== null;
	if (!hasEngine) {
		engineBox.style.display = "none";
		engineBox.innerHTML = "";
		return;
	}
	const cp = Number(opening.engine_cp);
	const pEngine = Number(opening.p_engine);
	const human = Number(opening.human_win_rate);
	const delta = Number(opening.delta);
	const interpretation = opening.interpretation || "";
	const cpLabel = cp === 0 ? "Equal position" : cp > 0 ? `White better by ${Math.abs(cp)} cp` : `Black better by ${Math.abs(cp)} cp`;
	const deltaSign = delta >= 0 ? "+" : "";
	const deltaColor = delta > 0.01 ? "#7BE495" : delta < -0.01 ? "#F28DA6" : TEXT_SECONDARY;
	const deltaLabel = delta > 0.01 ? "Humans overperform engine expectation" : delta < -0.01 ? "Humans underperform engine expectation" : "Humans match engine expectation";
	engineBox.style.display = "block";
	// Safe to keep as innerHTML: interpretation comes only from engine_delta._interpret(), which returns fixed strings.
	engineBox.innerHTML = `<h3 style="margin:0 0 1rem;">Engine vs Human</h3><div class="engine-cards"><div class="engine-card"><p style="margin:0 0 0.2rem;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;color:${TEXT_SECONDARY};">Engine says</p><p style="margin:0;font-size:1.1rem;font-weight:700;">${cpLabel}</p><p style="margin:0.2rem 0 0;font-size:0.78rem;color:${TEXT_SECONDARY};">Win probability: ${(pEngine * 100).toFixed(1)}%</p></div><div class="engine-card"><p style="margin:0 0 0.2rem;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;color:${TEXT_SECONDARY};">Humans achieve</p><p style="margin:0;font-size:1.1rem;font-weight:700;">${(human * 100).toFixed(1)}%</p><p style="margin:0.2rem 0 0;font-size:0.78rem;color:${TEXT_SECONDARY};">win rate (2000+ Elo, depth 20)</p></div></div><div style="border-left:3px solid ${deltaColor};padding:0.6rem 1rem;background:rgba(255,255,255,0.03);border-radius:0 6px 6px 0;"><p style="margin:0 0 0.15rem;font-size:0.78rem;font-weight:600;color:${deltaColor};">${deltaLabel}</p><p style="margin:0;font-size:0.82rem;color:${TEXT_SECONDARY};">Gap: <strong style="color:${TEXT_PRIMARY};">${deltaSign}${(delta * 100).toFixed(2)}%</strong>${interpretation ? ` &nbsp;·&nbsp; ${interpretation}` : ""}</p></div>`;
}

async function init() {
	syncBackLink();
	try {
		const data = await loadOpeningsData();
		const openingLines = await loadOpeningLines();
		const eco = resolveEco(data);
		if (!eco) {
			document.getElementById("opening-title").textContent = "No opening data available";
			return;
		}
		renderOpening(eco, data[eco], openingLines);
	} catch (error) {
		document.getElementById("opening-title").textContent = "Failed to load opening data";
		const narrativeEl = document.querySelector("#opening-narrative p");
		narrativeEl.textContent = String(error);
		narrativeEl.style.color = TEXT_SECONDARY;
		document.getElementById("opening-narrative").style.display = "";
	}
}

init();