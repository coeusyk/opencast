def _nav_html(current: str) -> str:
    pages = [
        ("index.html", "Overview"),
        ("openings.html", "Openings"),
        ("families.html", "Families"),
    ]
    links = ""
    for href, label in pages:
        active = ' class="nav-link active"' if href == current else ' class="nav-link"'
        links += f'<a href="{href}"{active}>{label}</a>\n    '

    return f"""<nav id="main-nav" class="site-nav">
  <div class="nav-inner">
    <a href="index.html" class="brand-lockup" aria-label="OpenCast home">
      <img src="assets/opencast_icon.png" alt="OpenCast logo" class="brand-logo" />
      <span class="nav-wordmark">OpenCast</span>
    </a>
    <button type="button" class="nav-toggle" aria-label="Toggle navigation" aria-expanded="false" aria-controls="site-nav-links">
      <span class="nav-toggle-bar"></span>
      <span class="nav-toggle-bar"></span>
      <span class="nav-toggle-bar"></span>
    </button>
    <div id="site-nav-links" class="nav-links">
    {links}
    </div>
  </div>
</nav>"""


def _page_shell(title: str, nav_fragment: str, body: str, head_extras: str = "") -> str:
    nav_css = """
<style>
/* Site nav */
.site-nav {
  position: sticky; top: 0; z-index: 100;
  background: rgba(11,13,16,0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255,255,255,0.07);
  height: 52px;
}
.nav-inner {
  max-width: 1200px; margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
  padding: 0 1rem; height: 100%;
  display: flex; align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.brand-lockup {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  text-decoration: none;
}
.brand-logo {
  width: 24px;
  height: 24px;
  object-fit: contain;
  border-radius: 4px;
}
.nav-wordmark {
  font-family: 'Satoshi', 'Inter', sans-serif;
  font-weight: 700; font-size: 1.05rem;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}
.nav-links { display: flex; gap: 1.5rem; align-items: center; }
.nav-toggle {
  display: none;
  width: 2.5rem;
  height: 2.5rem;
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 6px;
  background: rgba(255,255,255,0.02);
  color: var(--text-primary);
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 0.25rem;
}
.nav-toggle-bar {
  display: block;
  width: 1rem;
  height: 2px;
  border-radius: 999px;
  background: currentColor;
}
.nav-link {
  font-size: 0.875rem; font-weight: 500;
  color: var(--text-secondary); text-decoration: none;
  padding: 0.45rem 0.15rem;
  transition: color 150ms;
}
.nav-link:hover, .nav-link.active { color: var(--text-primary); }
body { font-family: 'Satoshi', 'Inter', sans-serif; }

@media (max-width: 760px) {
  .nav-inner {
    padding: 0 0.75rem;
  }
  .nav-toggle {
    display: inline-flex;
  }
  .nav-links {
    position: absolute;
    top: calc(100% + 0.45rem);
    right: 0.75rem;
    left: 0.75rem;
    display: none;
    flex-direction: column;
    align-items: stretch;
    gap: 0.15rem;
    background: rgba(11,13,16,0.98);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px;
    padding: 0.45rem;
  }
  .nav-links.open {
    display: flex;
  }
  .nav-link {
    display: block;
    font-size: 0.92rem;
    padding: 0.65rem 0.6rem;
    border-radius: 6px;
  }
}
</style>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — OpenCast</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300..600&display=swap" rel="stylesheet">
  <link href="https://api.fontshare.com/v2/css?f[]=satoshi@700,600,500,400&display=swap" rel="stylesheet">
  <link rel="icon" type="image/png" href="assets/opencast_icon.png">
  <link rel="apple-touch-icon" href="assets/opencast_icon.png">
  <link rel="stylesheet" href="assets/shared.css">
  {nav_css}
  {head_extras}
</head>
<body>
{nav_fragment}
<main><div class="page-content">
{body}
</div></main>
<script src="assets/nav.js"></script>
<script>
(() => {{
  const toggle = document.querySelector('.nav-toggle');
  const links = document.getElementById('site-nav-links');
  if (!toggle || !links) return;

  const closeMenu = () => {{
    links.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
  }};

  toggle.addEventListener('click', () => {{
    const isOpen = links.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  }});

  document.addEventListener('click', (event) => {{
    if (!event.target) return;
    if (toggle.contains(event.target) || links.contains(event.target)) return;
    closeMenu();
  }});

  window.addEventListener('resize', () => {{
    if (window.innerWidth > 760) closeMenu();
  }});
}})();
</script>
</body>
</html>
"""