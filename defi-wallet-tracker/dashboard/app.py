"""DeFi Smart Money Dashboard — Streamlit app.

Run with: streamlit run dashboard/app.py
Or via:   defi-tracker dashboard
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DeFi Smart Money Tracker",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path(__file__).parent.parent / "data"
SCAN_FILES = sorted(DATA_DIR.glob("scan_*.json"), reverse=True)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .metric-value { font-size: 2rem; font-weight: 700; color: #00d4aa; }
    .metric-label { font-size: 0.85rem; color: #8892a4; margin-top: 4px; }
    .wallet-tag {
        background: #0f3460;
        border-radius: 6px;
        padding: 3px 8px;
        font-size: 0.75rem;
        font-family: monospace;
        color: #00d4aa;
    }
    .win-high { color: #00d4aa; font-weight: 600; }
    .win-med  { color: #f0a500; font-weight: 600; }
    .win-low  { color: #e94560; font-weight: 600; }
    .score-bar { height: 6px; border-radius: 3px; background: #0f3460; }
    .score-fill { height: 6px; border-radius: 3px; background: linear-gradient(90deg, #00d4aa, #0080ff); }
    [data-testid="stSidebar"] { background: #0d1117; }
    .stDataFrame { font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_scan_file(path: str) -> tuple[list[dict], str]:
    with open(path) as f:
        d = json.load(f)
    wallets = d.get("wallets", d if isinstance(d, list) else [])
    generated = d.get("generated_at", "")
    return wallets, generated


def wallets_to_df(wallets: list[dict]) -> pd.DataFrame:
    rows = []
    for w in wallets:
        chains = w.get("chain") or (w.get("chains") or ["?"])[0]
        rows.append({
            "Address":        w.get("address", ""),
            "Chain":          chains,
            "Score":          float(w.get("score", 0)),
            "Win Rate %":     float(w.get("win_rate", 0)),
            "Trades":         int(w.get("total_trades", 0)),
            "Avg Mult":       float(w.get("avg_multiplier", 0)),
            "Max Mult":       float(w.get("max_multiplier", 0)),
            "Early (≥5x)":   int(w.get("early_entries", 0)),
            "Best Entry":     float(w.get("best_early_entry_x", 0)),
            "Best Token":     w.get("best_early_token", ""),
            "Total PnL $":    float(w.get("total_pnl_usd", 0)),
            "Source":         w.get("source", ""),
        })
    return pd.DataFrame(rows)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧠 Smart Money Tracker")
    st.markdown("---")

    # File selector
    file_labels = {str(f): f.name for f in SCAN_FILES}
    if not SCAN_FILES:
        st.error("No scan files found in data/")
        st.info("Run: `defi-tracker scan --json data/scan_latest.json`")
        st.stop()

    selected_file = st.selectbox(
        "Scan file",
        options=list(file_labels.keys()),
        format_func=lambda x: file_labels[x],
    )

    wallets_raw, generated_at = load_scan_file(selected_file)

    if generated_at:
        try:
            dt = datetime.fromisoformat(generated_at)
            age_min = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
            age_str = f"{age_min}m ago" if age_min < 60 else f"{age_min//60}h {age_min%60}m ago"
            st.caption(f"Generated {age_str}")
        except Exception:
            st.caption(generated_at[:19])

    st.markdown("---")

    # Filters
    st.markdown("### Filters")

    chains_available = sorted({w.get("chain") or (w.get("chains") or ["?"])[0] for w in wallets_raw})
    selected_chains = st.multiselect("Chains", chains_available, default=chains_available)

    min_score = st.slider("Min Score", 0, 120, 0, step=5)
    min_win_rate = st.slider("Min Win Rate %", 0, 100, 0, step=5)
    min_early = st.slider("Min Early Entries (≥5x)", 0, 10, 0, step=1)

    st.markdown("---")
    st.markdown("### Run New Scan")
    scan_chain = st.selectbox("Chain", ["eth", "bsc", "base", "arbitrum", "solana", "all"])
    scan_mult = st.number_input("Min Multiplier", value=5.0, step=0.5)
    scan_wr = st.number_input("Min Win Rate", value=85.0, step=5.0)
    if st.button("🔍 Start Scan", use_container_width=True):
        cmd = [
            sys.executable, "-m", "src.main", "scan",
            "--min-mult", str(scan_mult),
            "--min-win-rate", str(scan_wr),
            "--json", "data/scan_latest.json",
        ]
        if scan_chain == "all":
            for c in ["eth", "bsc", "base", "arbitrum", "solana"]:
                cmd += ["--chain", c]
        else:
            cmd += ["--chain", scan_chain]
        with st.spinner("Scanning... (2-5 minutes)"):
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    cwd=Path(__file__).parent.parent)
        if result.returncode == 0:
            st.success("Scan complete! Refresh the page.")
            st.cache_data.clear()
        else:
            st.error(f"Scan failed:\n{result.stderr[-500:]}")


# ── Apply filters ─────────────────────────────────────────────────────────────
df_all = wallets_to_df(wallets_raw)
df = df_all[
    df_all["Chain"].isin(selected_chains) &
    (df_all["Score"] >= min_score) &
    (df_all["Win Rate %"] >= min_win_rate) &
    (df_all["Early (≥5x)"] >= min_early)
].copy()

df = df.sort_values("Score", ascending=False).reset_index(drop=True)
df.index = df.index + 1  # 1-based rank


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("# 🧠 DeFi Smart Money Leaderboard")
st.markdown(f"*{len(df)} wallets matching filters · {len(df_all)} total in scan*")

# ── Summary metrics ───────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Total Wallets", len(df_all))
with c2:
    wr_vals = df_all["Win Rate %"][df_all["Win Rate %"] > 0]
    st.metric("Avg Win Rate", f"{wr_vals.mean():.1f}%" if len(wr_vals) else "—")
with c3:
    st.metric("Best Entry", f"{df_all['Best Entry'].max():.1f}x")
with c4:
    st.metric("Max PnL", f"${df_all['Total PnL $'].max():,.0f}")
with c5:
    multi_entry = (df_all["Early (≥5x)"] >= 2).sum()
    st.metric("Multi-Entry Wallets", multi_entry)

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_lb, tab_charts, tab_wallet = st.tabs(["🏆 Leaderboard", "📊 Analytics", "🔍 Wallet Detail"])


# ── Tab 1: Leaderboard ────────────────────────────────────────────────────────
with tab_lb:
    if df.empty:
        st.warning("No wallets match the current filters.")
    else:
        # Display options
        col_left, col_right = st.columns([3, 1])
        with col_right:
            top_n = st.selectbox("Show top", [25, 50, 100, 200], index=1)

        display_df = df.head(top_n).copy()

        # Format address as short
        display_df["Wallet"] = display_df["Address"].apply(
            lambda a: f"{a[:8]}…{a[-6:]}" if len(a) > 14 else a
        )

        # Color-coded win rate
        def fmt_wr(v):
            if v >= 90:   return f"🟢 {v:.1f}%"
            if v >= 75:   return f"🟡 {v:.1f}%"
            if v > 0:     return f"🔴 {v:.1f}%"
            return "—"

        display_df["Win Rate"] = display_df["Win Rate %"].apply(fmt_wr)
        display_df["Best"] = display_df.apply(
            lambda r: f"{r['Best Entry']:.1f}x {r['Best Token'][:6]}" if r["Best Token"] else f"{r['Best Entry']:.1f}x",
            axis=1
        )
        display_df["PnL"] = display_df["Total PnL $"].apply(
            lambda v: f"${v:,.0f}" if v != 0 else "—"
        )
        display_df["Score"] = display_df["Score"].apply(lambda v: f"{v:.1f}")

        show_cols = ["Wallet", "Chain", "Score", "Win Rate", "Trades",
                     "Early (≥5x)", "Best", "PnL", "Source"]

        st.dataframe(
            display_df[show_cols],
            use_container_width=True,
            height=min(60 + len(display_df) * 35, 700),
        )

        # Copy-friendly address list
        with st.expander("📋 Copy wallet addresses"):
            addrs = "\n".join(df.head(top_n)["Address"].tolist())
            st.code(addrs, language=None)


# ── Tab 2: Analytics ──────────────────────────────────────────────────────────
with tab_charts:
    if df.empty:
        st.warning("No data to chart.")
    else:
        row1_c1, row1_c2 = st.columns(2)

        with row1_c1:
            fig = px.histogram(
                df[df["Win Rate %"] > 0],
                x="Win Rate %",
                nbins=20,
                title="Win Rate Distribution",
                color_discrete_sequence=["#00d4aa"],
                template="plotly_dark",
            )
            fig.update_layout(
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                showlegend=False, margin=dict(t=40, b=20, l=20, r=20),
            )
            st.plotly_chart(fig, use_container_width=True)

        with row1_c2:
            fig2 = px.scatter(
                df[df["Trades"] > 0],
                x="Trades", y="Win Rate %",
                size="Score", color="Early (≥5x)",
                hover_data=["Address", "Best Entry", "Best Token"],
                title="Win Rate vs Trade Count",
                color_continuous_scale="teal",
                template="plotly_dark",
            )
            fig2.update_layout(
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                margin=dict(t=40, b=20, l=20, r=20),
            )
            st.plotly_chart(fig2, use_container_width=True)

        row2_c1, row2_c2 = st.columns(2)

        with row2_c1:
            entry_counts = df["Early (≥5x)"].value_counts().sort_index()
            fig3 = px.bar(
                x=entry_counts.index.astype(str),
                y=entry_counts.values,
                title="Early Entry Count Distribution",
                labels={"x": "# Tokens Caught Early (≥5x)", "y": "Wallets"},
                color=entry_counts.values,
                color_continuous_scale="teal",
                template="plotly_dark",
            )
            fig3.update_layout(
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                showlegend=False, coloraxis_showscale=False,
                margin=dict(t=40, b=20, l=20, r=20),
            )
            st.plotly_chart(fig3, use_container_width=True)

        with row2_c2:
            # Best token leaderboard
            token_counts = df[df["Best Token"] != ""]["Best Token"].value_counts().head(10)
            fig4 = px.bar(
                x=token_counts.values,
                y=token_counts.index,
                orientation="h",
                title="Most Caught Tokens (Best Entry)",
                labels={"x": "Wallets", "y": "Token"},
                color=token_counts.values,
                color_continuous_scale="teal",
                template="plotly_dark",
            )
            fig4.update_layout(
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                showlegend=False, coloraxis_showscale=False,
                yaxis=dict(autorange="reversed"),
                margin=dict(t=40, b=20, l=20, r=20),
            )
            st.plotly_chart(fig4, use_container_width=True)

        # Score vs Best Entry scatter
        fig5 = px.scatter(
            df,
            x="Best Entry", y="Score",
            color="Win Rate %",
            size="Early (≥5x)",
            size_max=20,
            hover_data=["Address", "Trades", "Best Token", "Total PnL $"],
            title="Score vs Best Entry Multiplier",
            color_continuous_scale="RdYlGn",
            template="plotly_dark",
        )
        fig5.update_layout(
            paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
            margin=dict(t=40, b=20, l=20, r=20),
        )
        st.plotly_chart(fig5, use_container_width=True)


# ── Tab 3: Wallet Detail ──────────────────────────────────────────────────────
with tab_wallet:
    st.markdown("### Inspect a Wallet")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        wallet_input = st.text_input(
            "Wallet address",
            placeholder="0x... or select from leaderboard",
            label_visibility="collapsed",
        )
    with col_btn:
        lookup = st.button("Look up", use_container_width=True)

    # Quick-select from top wallets
    st.markdown("**Quick select from leaderboard:**")
    top_addrs = df.head(20)["Address"].tolist()
    cols = st.columns(4)
    selected_quick = None
    for i, addr in enumerate(top_addrs):
        if cols[i % 4].button(f"#{i+1} {addr[:8]}…{addr[-4:]}", key=f"qs_{i}"):
            selected_quick = addr

    wallet_addr = selected_quick or (wallet_input.strip() if lookup else None)

    if wallet_addr:
        # Find in current data
        matches = [w for w in wallets_raw if w.get("address", "").lower() == wallet_addr.lower()]

        if matches:
            w = matches[0]
            st.markdown("---")
            st.markdown(f"### `{w['address']}`")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Score", f"{w.get('score', 0):.1f}")
            m2.metric("Win Rate", f"{w.get('win_rate', 0):.1f}%")
            m3.metric("Total Trades", w.get("total_trades", 0))
            m4.metric("Total PnL", f"${w.get('total_pnl_usd', 0):,.0f}")

            m5, m6, m7, m8 = st.columns(4)
            m5.metric("Early Entries", w.get("early_entries", 0))
            m6.metric("Best Entry", f"{w.get('best_early_entry_x', 0):.1f}x")
            m7.metric("Avg Multiplier", f"{w.get('avg_multiplier', 0):.2f}x")
            m8.metric("Max Multiplier", f"{w.get('max_multiplier', 0):.1f}x")

            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Details**")
                st.write(f"- **Chain:** {w.get('chain') or ', '.join(w.get('chains', []))}")
                st.write(f"- **Source:** {w.get('source', '—')}")
                st.write(f"- **Best Token:** {w.get('best_early_entry_x', 0):.1f}x — {w.get('best_early_token', '—')}")
                if w.get("winning_trades", 0) or w.get("losing_trades", 0):
                    st.write(f"- **W/L:** {w['winning_trades']}W / {w['losing_trades']}L")
                if w.get("active_since"):
                    st.write(f"- **Active since:** {w['active_since'][:10]}")
                if w.get("last_active"):
                    st.write(f"- **Last active:** {w['last_active'][:10]}")

            with col_b:
                # Performance radar chart
                categories = ["Win Rate", "Early Entries", "Best Entry", "Avg Mult", "Score"]
                # Normalize each to 0-100
                max_vals = {"Win Rate": 100, "Early Entries": 10, "Best Entry": 50, "Avg Mult": 20, "Score": 120}
                vals = [
                    min(w.get("win_rate", 0), 100),
                    min(w.get("early_entries", 0) * 10, 100),
                    min(w.get("best_early_entry_x", 0) / max_vals["Best Entry"] * 100, 100),
                    min(w.get("avg_multiplier", 0) / max_vals["Avg Mult"] * 100, 100),
                    min(w.get("score", 0) / max_vals["Score"] * 100, 100),
                ]
                fig_radar = go.Figure(go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=categories + [categories[0]],
                    fill="toself",
                    fillcolor="rgba(0, 212, 170, 0.2)",
                    line=dict(color="#00d4aa", width=2),
                ))
                fig_radar.update_layout(
                    polar=dict(
                        bgcolor="#0d1117",
                        radialaxis=dict(visible=True, range=[0, 100], showticklabels=False),
                        angularaxis=dict(color="#8892a4"),
                    ),
                    paper_bgcolor="#0d1117",
                    showlegend=False,
                    margin=dict(t=20, b=20, l=20, r=20),
                    height=280,
                )
                st.plotly_chart(fig_radar, use_container_width=True)

            # External links
            chain = w.get("chain") or (w.get("chains") or ["eth"])[0]
            addr = w["address"]
            st.markdown("**View on-chain:**")
            links = {
                "eth": f"https://etherscan.io/address/{addr}",
                "bsc": f"https://bscscan.com/address/{addr}",
                "base": f"https://basescan.org/address/{addr}",
                "arbitrum": f"https://arbiscan.io/address/{addr}",
                "solana": f"https://solscan.io/account/{addr}",
            }
            explorer_url = links.get(chain, f"https://etherscan.io/address/{addr}")
            st.markdown(
                f"[🔗 Explorer]({explorer_url}) &nbsp;&nbsp; "
                f"[🦅 Debank](https://debank.com/profile/{addr}) &nbsp;&nbsp; "
                f"[📊 Zapper](https://zapper.xyz/account/{addr})"
            )

        else:
            st.info(f"`{wallet_addr}` not in current scan. Try running a new scan or check another file.")
            chain_sel = st.selectbox("Look up on chain", ["eth", "bsc", "base", "arbitrum", "solana"])
            addr = wallet_addr
            links = {
                "eth": f"https://etherscan.io/address/{addr}",
                "bsc": f"https://bscscan.com/address/{addr}",
                "base": f"https://basescan.org/address/{addr}",
                "arbitrum": f"https://arbiscan.io/address/{addr}",
                "solana": f"https://solscan.io/account/{addr}",
            }
            st.markdown(f"[🔗 View on Explorer]({links[chain_sel]})")
