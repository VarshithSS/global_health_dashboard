"""Rebuild the CS661 Group-5 project report end to end.

    python report/build_report.py            # figures + PDF
    python report/build_report.py --pdf-only # skip figure regeneration

Chart figures are rendered by importing the dashboard's own theme and
create_*() functions, so the figures in the report are produced by the same
code paths the live app uses. The three interface screenshots additionally
need a running app and Playwright; they are only re-captured with --shots.
"""
import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "report"
FIGS = HERE / "figures"
APP_URL = "http://127.0.0.1:8050/"
PANEL = "#ffffff"          # dashboard card surface (the chart surface)


def build_charts():
    sys.path.insert(0, str(ROOT))
    import app as A

    FIGS.mkdir(parents=True, exist_ok=True)

    def save(fig, name, w, h):
        fig.update_layout(paper_bgcolor=PANEL, plot_bgcolor=PANEL)
        if fig.layout.geo is not None:
            fig.update_geos(bgcolor=PANEL)
        fig.write_image(str(FIGS / f"{name}.png"), width=w, height=h, scale=2)
        print("  ", name)

    print("Rendering task figures...")
    save(A._fig_map("diab_tx_std", 2022, "Female", A.ALL_TOKEN, A.ALL_TOKEN),
         "task1_map", 1500, 820)
    save(A._fig_sexgap("htn_tx_std", "India"), "task2_sexgap", 1200, 900)
    save(A._fig_trend("income", "htn_ctrl_std",
                      ("High-income", "Upper-middle-income",
                       "Lower-middle-income", "Low-income"), None),
         "task3_trend", 1400, 850)
    save(A._fig_cascade("India", 2019, "Female"), "task4_cascade", 1300, 800)
    save(A._fig_region("diab_tx_std", 2022), "task5_regionincome", 1450, 900)
    save(A._fig_agecrude("hypertension_treatment", 2019, "Female",
                         ("Japan", "Qatar", "United Arab Emirates",
                          "Denmark", "India")),
         "task6_agecrude", 1200, 950)


def build_screenshots():
    """Capture the interface figures. Requires `python app.py` to be running."""
    from playwright.sync_api import sync_playwright

    hide_debug = "[class*='dash-debug']{display:none !important;}"
    print(f"Capturing interface screenshots from {APP_URL} ...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1680, "height": 1150},
                                device_scale_factor=2)
        page.goto(APP_URL, wait_until="networkidle")
        page.wait_for_timeout(5000)          # let Plotly paint the choropleth
        page.add_style_tag(content=hide_debug)

        page.screenshot(path=str(FIGS / "ui_overview.png"), full_page=True)
        page.screenshot(path=str(FIGS / "ui_kpi_strip.png"),
                        clip={"x": 34, "y": 100, "width": 1612, "height": 286})
        page.click("#nav-4")                 # switch to the Care Cascade view
        page.wait_for_timeout(3500)
        page.add_style_tag(content=hide_debug)
        page.screenshot(path=str(FIGS / "ui_cascade_view.png"), full_page=True)
        browser.close()
    print("   ui_overview, ui_kpi_strip, ui_cascade_view")


def build_pdf():
    from weasyprint import HTML
    out = HERE / "CS661_Group5_Project_Report.pdf"
    HTML(str(HERE / "report.html")).write_pdf(str(out))
    print(f"PDF -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-only", action="store_true",
                    help="skip figure regeneration")
    ap.add_argument("--shots", action="store_true",
                    help="also re-capture UI screenshots (needs the app running)")
    args = ap.parse_args()

    if not args.pdf_only:
        build_charts()
    if args.shots:
        build_screenshots()
    build_pdf()
