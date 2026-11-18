import json
import math
import uuid
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ==============================================================================
# CAREER VENTURE LAB - PATHWAY MKT-3 (AP CALCULUS | MARKETING AGENCY)
# Stage 1 Core Engine: Deterministic Math, Dated Ledger, Save/Load, & Tests
# ==============================================================================

st.set_page_config(
    page_title="Career Venture Lab | MKT-3 Agency Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- DEFAULT MKT-3 BASELINE CONSTANTS (Handbook Pages 40, 70, 98-102) ---
DEFAULT_STATE = {
    "team_id": "TEAM-MKT-01",
    "course": "AP Calculus",
    "pathway_id": "MKT-3",
    "business_name": "Local-Business Marketing Agency",
    "selected_level": "Applied",  # Foundation | Applied | Advanced
    "snapshot_id": "SNAP-0001",
    "state_version": 1,
    "simulation_date": "2027-01-31",
    "base_period": "monthly",
    "working_days": 22,
    "currency": "USD",
    "random_seed": 2027,
    "assumptions": [
        "All figures are fictional teaching defaults from Career Venture Lab MKT-3.",
        "Revenue is recognized only on completed packages, capped by monthly capacity.",
        "Startup equipment ($1,500) is an asset; pre-opening setup ($1,000) is recorded at start.",
        "Client pass-through ad budgets are excluded from agency profit.",
    ],
    "sources": ["Career Venture Lab Student Handbook (Revised Nov 2026), Pathway MKT-3"],
    "funding": {
        "owner_contribution": 6500.00,
        "equipment_assets": 1500.00,
        "pre_opening_expense": 1000.00,
        "opening_cash": 4000.00,
        "loan_principal": 0.00,
        "interest_rate_monthly": 0.00,
    },
    "inputs": {
        "base_price": 250.00,
        "D0": 12,
        "staff_hours": 80.0,
        "hours_per_unit": 8.0,
        "revision_hours_per_package": 0.0,
        "extra_revision_hourly_cost": 5.00,
        "own_ad_spend": 0.00,
        "client_media_budget": 0.00,
        "refund_amount": 0.00,
        "additional_capex": 0.00,
    },
    "variable_cost_lines": {
        "designer_labor": 40.00,
        "licensed_assets": 10.00,
        "printing_delivery": 20.00,
        "quality_revision_allowance": 10.00,
    },
    "fixed_cost_lines": {
        "software": 250.00,
        "workspace": 300.00,
        "admin": 200.00,
        "hosting": 150.00,
    },
    "cash": 4000.00,
    "debt": 0.00,
    "ledger": [],
    "processed_run_ids": [],
    "processed_campaign_ids": [],
    "decisions": [],
}

MONTHLY_FIXTURE = pd.DataFrame([
    {"month": "2027-01", "requested": 12, "capacity_override": 10, "ad_cost": 0.00},
    {"month": "2027-02", "requested": 13, "capacity_override": 10, "ad_cost": 100.00},
    {"month": "2027-03", "requested": 11, "capacity_override": 7, "ad_cost": 0.00},
])


def init_state():
    if "biz_state" not in st.session_state:
        st.session_state.biz_state = json.loads(json.dumps(DEFAULT_STATE))


def reset_state():
    team_id = st.session_state.biz_state.get("team_id", "TEAM-MKT-01")
    level = st.session_state.biz_state.get("selected_level", "Applied")
    st.session_state.biz_state = json.loads(json.dumps(DEFAULT_STATE))
    st.session_state.biz_state["team_id"] = team_id
    st.session_state.biz_state["selected_level"] = level


def compute_metrics(state, requested_override=None, capacity_override=None, ad_override=None):
    inp = state["inputs"]
    vlines = state["variable_cost_lines"]
    flines = state["fixed_cost_lines"]

    price = float(inp["base_price"])
    requested = int(inp["D0"] if requested_override is None else requested_override)
    staff_hours = float(inp["staff_hours"])
    hours_per_unit = float(inp["hours_per_unit"])
    rev_hours = float(inp["revision_hours_per_package"])
    extra_rev_cost = float(inp["extra_revision_hourly_cost"])

    total_hours_per_unit = hours_per_unit + rev_hours
    derived_capacity = int(math.floor(staff_hours / total_hours_per_unit)) if total_hours_per_unit > 0 else 0
    capacity = int(capacity_override) if capacity_override is not None else derived_capacity

    sold = min(max(0, requested), max(0, capacity))
    unserved_demand = max(0, requested - sold)

    base_var_unit = sum(float(x) for x in vlines.values())
    variable_per_unit = round(base_var_unit + (rev_hours * extra_rev_cost), 2)
    fixed_total = round(sum(float(x) for x in flines.values()), 2)
    marketing = round(float(inp["own_ad_spend"] if ad_override is None else ad_override), 2)
    refunds = round(float(inp["refund_amount"]), 2)
    capex = round(float(inp["additional_capex"]), 2)

    gross_revenue = round(price * sold, 2)
    net_revenue = round(gross_revenue - refunds, 2)
    variable_expense = round(sold * variable_per_unit, 2)
    operating_profit = round(net_revenue - variable_expense - fixed_total - marketing, 2)
    net_cash_change = round(operating_profit - capex, 2)

    return {
        "price": price,
        "requested": requested,
        "derived_capacity": derived_capacity,
        "capacity": capacity,
        "sold": sold,
        "unserved_demand": unserved_demand,
        "variable_per_unit": variable_per_unit,
        "fixed_total": fixed_total,
        "marketing": marketing,
        "refunds": refunds,
        "capex": capex,
        "gross_revenue": gross_revenue,
        "net_revenue": net_revenue,
        "variable_expense": variable_expense,
        "total_operating_expense": round(variable_expense + fixed_total + marketing, 2),
        "operating_profit": operating_profit,
        "net_cash_change": net_cash_change,
    }


def record_simulation_step(state, run_id, sim_date, metrics, mode="Normal", campaign_id=None):
    """Idempotent ledger writer: prevents duplicate runs or duplicate campaign charges."""
    if run_id in state["processed_run_ids"]:
        return False, f"Duplicate run_id '{run_id}' rejected. No transactions created."

    if campaign_id and metrics["marketing"] > 0:
        if campaign_id in state["processed_campaign_ids"]:
            return False, f"Duplicate campaign_id '{campaign_id}' rejected. Campaign already charged."
        state["processed_campaign_ids"].append(campaign_id)

    v = state["state_version"]
    tx_base = f"TX-v{v}-{len(state['ledger']) + 1:04d}"

    entries = [
        {
            "transaction_id": f"{tx_base}-REV",
            "run_id": run_id,
            "date": sim_date,
            "mode": mode,
            "event_type": "sales_revenue",
            "category": "Campaign Packages",
            "quantity": metrics["sold"],
            "unit_price": metrics["price"],
            "amount": metrics["net_revenue"],
            "state_version": v,
        },
        {
            "transaction_id": f"{tx_base}-VAR",
            "run_id": run_id,
            "date": sim_date,
            "mode": mode,
            "event_type": "variable_expense",
            "category": "Package Delivery Costs",
            "quantity": metrics["sold"],
            "unit_price": metrics["variable_per_unit"],
            "amount": -metrics["variable_expense"],
            "state_version": v,
        },
        {
            "transaction_id": f"{tx_base}-FIX",
            "run_id": run_id,
            "date": sim_date,
            "mode": mode,
            "event_type": "fixed_expense",
            "category": "Monthly Overhead",
            "quantity": 1,
            "unit_price": metrics["fixed_total"],
            "amount": -metrics["fixed_total"],
            "state_version": v,
        },
    ]

    if metrics["marketing"] > 0:
        entries.append({
            "transaction_id": f"{tx_base}-MKT",
            "run_id": run_id,
            "date": sim_date,
            "mode": mode,
            "event_type": "marketing_expense",
            "category": campaign_id or "Agency Promotion",
            "quantity": 1,
            "unit_price": metrics["marketing"],
            "amount": -metrics["marketing"],
            "state_version": v,
        })

    if metrics["capex"] > 0:
        entries.append({
            "transaction_id": f"{tx_base}-CAPEX",
            "run_id": run_id,
            "date": sim_date,
            "mode": mode,
            "event_type": "capital_expenditure",
            "category": "Equipment Purchase",
            "quantity": 1,
            "unit_price": metrics["capex"],
            "amount": -metrics["capex"],
            "state_version": v,
        })

    state["ledger"].extend(entries)
    state["cash"] = round(state["cash"] + metrics["net_cash_change"], 2)
    state["processed_run_ids"].append(run_id)
    state["state_version"] += 1
    state["snapshot_id"] = f"SNAP-{state['state_version']:04d}"
    state["simulation_date"] = sim_date
    return True, f"Recorded run '{run_id}' -> Advanced to state v{state['state_version']}."


init_state()
state = st.session_state.biz_state

# ==============================================================================
# SIDEBAR: IDENTITY, SNAPSHOT EXPORT/IMPORT, & LEVEL CONTROL
# ==============================================================================
with st.sidebar:
    st.title("Career Venture Lab")
    st.caption(f"**{state['pathway_id']}** | {state['course']}")

    state["team_id"] = st.text_input("Team ID", value=state["team_id"])
    state["selected_level"] = st.selectbox(
        "Teacher-Approved Math Level",
        ["Foundation", "Applied", "Advanced"],
        index=["Foundation", "Applied", "Advanced"].index(state["selected_level"]),
    )

    st.divider()
    st.markdown(f"**Snapshot ID:** `{state['snapshot_id']}`")
    st.markdown(f"**State Version:** `v{state['state_version']}`")
    st.markdown(f"**Cash on Hand:** `${state['cash']:,.2f}`")
    if state["cash"] < 800:
        st.warning("Finance Flag: Cash reserve is below $800!")

    st.divider()
    st.subheader("Save / Restore State (JSON)")
    snapshot_json = json.dumps(state, indent=2)
    st.download_button(
        label="Export Snapshot JSON",
        data=snapshot_json,
        file_name=f"{state['team_id']}_{state['pathway_id']}_v{state['state_version']}.json",
        mime="application/json",
    )

    uploaded_file = st.file_uploader("Import Snapshot JSON", type=["json"])
    if uploaded_file is not None:
        try:
            imported = json.load(uploaded_file)
            if imported.get("team_id") != state["team_id"]:
                st.error(
                    f"Rejected Import: Team ID mismatch (expected '{state['team_id']}', got '{imported.get('team_id')}')."
                )
            elif imported.get("pathway_id") != "MKT-3":
                st.error("Rejected Import: Pathway must be MKT-3.")
            elif int(imported.get("state_version", 0)) < int(state["state_version"]):
                st.error(
                    f"Rejected Stale Snapshot: Imported v{imported.get('state_version')} is older than current v{state['state_version']}."
                )
            else:
                st.session_state.biz_state = imported
                st.success(f"Restored {imported.get('snapshot_id')} (v{imported.get('state_version')}).")
                st.rerun()
        except Exception as exc:
            st.error(f"Invalid JSON file: {exc}")

    if st.button("Reset to Opening Baseline"):
        reset_state()
        st.rerun()

# ==============================================================================
# MAIN TABS (STAGE 1 CORE + ROADMAP PLACEHOLDERS)
# ==============================================================================
st.title("Local-Business Marketing Agency (MKT-3)")
st.caption(
    "Stage 1 Core Engine: Deterministic Business Math, AP Calculus Optimization, Dated Ledger, & Acceptance Tests"
)

tabs = st.tabs([
    "1. Overview & Inputs",
    "2. AP Calculus Math Panel",
    "3. Ledger & Simulation Run",
    "4. Acceptance Tests & Fixtures",
    "5. Stage 2-3 Roadmap",
])

# ------------------------------------------------------------------------------
# TAB 1: OVERVIEW & EDITABLE BUSINESS INPUTS
# ------------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Current Business Snapshot & Editable Assumptions")
    st.info(
        "Plain-Language Guide: Changing sliders below previews your monthly numbers immediately. "
        "Nothing changes your official Cash on Hand or Ledger until you approve and record a run in Tab 3."
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("**Pricing & Demand**")
        state["inputs"]["base_price"] = st.number_input(
            "Package Price ($)", min_value=1.0, max_value=1000.0, value=float(state["inputs"]["base_price"]), step=10.0
        )
        state["inputs"]["D0"] = st.number_input(
            "Requested Packages / Month", min_value=0, max_value=200, value=int(state["inputs"]["D0"]), step=1
        )
        state["inputs"]["own_ad_spend"] = st.number_input(
            "Own-Agency Advertising ($)", min_value=0.0, max_value=5000.0, value=float(state["inputs"]["own_ad_spend"]), step=25.0
        )

    with col_b:
        st.markdown("**Staffing & Revision Capacity**")
        state["inputs"]["staff_hours"] = st.number_input(
            "Productive Staff Hours / Month", min_value=0.0, max_value=500.0, value=float(state["inputs"]["staff_hours"]), step=8.0
        )
        state["inputs"]["hours_per_unit"] = st.number_input(
            "Base Hours per Package", min_value=1.0, max_value=40.0, value=float(state["inputs"]["hours_per_unit"]), step=1.0
        )
        state["inputs"]["revision_hours_per_package"] = st.number_input(
            "Extra Revision Hours / Package", min_value=0.0, max_value=20.0, value=float(state["inputs"]["revision_hours_per_package"]), step=0.5
        )
        state["inputs"]["extra_revision_hourly_cost"] = st.number_input(
            "Extra Revision Cost ($/hr)", min_value=0.0, max_value=100.0, value=float(state["inputs"]["extra_revision_hourly_cost"]), step=1.0
        )

    with col_c:
        st.markdown("**Unit & Monthly Cost Lines**")
        with st.expander("Variable Costs ($/package)", expanded=False):
            for k, val in state["variable_cost_lines"].items():
                state["variable_cost_lines"][k] = st.number_input(
                    k.replace("_", " ").title(), min_value=0.0, value=float(val), step=5.0, key=f"var_{k}"
                )
        with st.expander("Fixed Costs ($/month)", expanded=False):
            for k, val in state["fixed_cost_lines"].items():
                state["fixed_cost_lines"][k] = st.number_input(
                    k.replace("_", " ").title(), min_value=0.0, value=float(val), step=25.0, key=f"fix_{k}"
                )
        state["inputs"]["client_media_budget"] = st.number_input(
            "Client Pass-Through Ad Budget ($ - Not Agency Revenue)",
            min_value=0.0,
            value=float(state["inputs"]["client_media_budget"]),
            step=50.0,
        )

    preview = compute_metrics(state)

    st.divider()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Monthly Capacity", f"{preview['capacity']} pkgs", f"{state['inputs']['staff_hours']:.0f} hrs avail")
    m2.metric("Completed Sales", f"{preview['sold']} pkgs", f"-{preview['unserved_demand']} unserved demand")
    m3.metric("Projected Revenue", f"${preview['net_revenue']:,.2f}")
    m4.metric("Total Monthly Expense", f"${preview['total_operating_expense']:,.2f}", f"${preview['variable_per_unit']:.2f}/pkg var")
    m5.metric("Operating Profit", f"${preview['operating_profit']:,.2f}")

# ------------------------------------------------------------------------------
# TAB 2: PERSISTENT AP CALCULUS MATH PANEL
# ------------------------------------------------------------------------------
with tabs[1]:
    level = state["selected_level"]
    st.subheader(f"AP Calculus Decision Panel — {level} Mode")

    p0 = 250.0
    D0 = 12.0
    a = 2 * D0  # 24
    b = D0 / p0  # 0.048
    v = preview["variable_per_unit"]
    F = preview["fixed_total"] + preview["marketing"]
    cap = preview["capacity"]

    # Corner price where q(p) = cap -> 24 - 0.048p = cap
    p_corner = (a - cap) / b if b > 0 else 0.0
    p_unconstrained_opt = (a + b * v) / (2 * b)
    p_max_domain = 2 * p0  # 500

    st.markdown(
        f"""
        * **Business Question:** What package price $p$ maximizes monthly profit while respecting our capacity ceiling of **{cap} packages**?
        * **Demand Function:** $q(p) = {a:.0f} - {b:.3f}p$ on domain $0 \le p \le {p_max_domain:.0f}$ (units: packages/month)
        * **Variable Cost ($v$):** `${v:.2f}/package` | **Fixed + Marketing Cost ($F$):** `${F:.2f}/month`
        """
    )

    prices = np.linspace(0, p_max_domain, 501)
    q_unconstrained = np.maximum(0.0, a - b * prices)
    s_constrained = np.minimum(float(cap), q_unconstrained)

    profit_unconstrained = (prices - v) * q_unconstrained - F
    profit_constrained = (prices - v) * s_constrained - F

    # Derivative P'(p)
    d_profit_unconstrained = a + b * v - 2 * b * prices
    d_profit_constrained = np.where(prices < p_corner, float(cap), a + b * v - 2 * b * prices)

    if level == "Foundation":
        st.info(
            "**Foundation Task:** Analyze the unconstrained quadratic profit function "
            "$P(p) = (p - v)(24 - 0.048p) - F$ and its derivative $P'(p) = 24 + 0.048v - 0.096p$."
        )
        opt_profit_unc = (p_unconstrained_opt - v) * (a - b * p_unconstrained_opt) - F
        st.write(
            f"- **Critical Point ($P'(p) = 0$):** $p = \frac{{{a:.0f} + {b:.3f}({v:.2f})}}{{2({b:.3f})}} = **\${p_unconstrained_opt:.2f}**$"
        )
        st.write(
            f"- **Unconstrained Demand at $p = \${p_unconstrained_opt:.2f}$:** $q = {a - b * p_unconstrained_opt:.2f}$ packages/month"
        )
        st.write(f"- **Unconstrained Maximum Profit:** `${opt_profit_unc:,.2f}`")
        st.warning(
            f"Check Feasibility: At $p = \${p_unconstrained_opt:.2f}$, demand is {a - b * p_unconstrained_opt:.2f} packages, "
            f"which exceeds our capacity of {cap} packages! Switch to **Applied** to enforce capacity."
        )

    elif level == "Applied":
        st.info(
            "**Applied Task:** Enforce completed sales $s(p) = \min(\text{capacity}, \max(0, 24 - 0.048p))$. "
            "Compare the capacity-constrained branch ($p < p_{\text{corner}}$) and demand branch ($p > p_{\text{corner}}$)."
        )
        # Evaluate candidate points: p=0, corner p_corner, unconstrained critical point (if feasible), endpoint p=500
        candidates = [
            ("Left Endpoint (p = $0)", 0.0),
            (f"Capacity Corner (q = {cap})", p_corner),
            ("Unconstrained Critical Point", p_unconstrained_opt),
            ("Right Endpoint (p = $500)", p_max_domain),
        ]
        rows = []
        for label, p_val in candidates:
            q_val = max(0.0, a - b * p_val)
            s_val = min(float(cap), q_val)
            prof_cont = (p_val - v) * s_val - F
            s_int = int(math.floor(s_val))
            prof_int = (p_val - v) * s_int - F
            feasible = "Yes (Interior)" if p_val > p_corner else ("Boundary" if abs(p_val - p_corner) < 1e-6 else "Capped by Capacity")
            rows.append({
                "Candidate Point": label,
                "Price ($)": round(p_val, 2),
                "Raw Demand q(p)": round(q_val, 2),
                "Continuous Sales s(p)": round(s_val, 2),
                "Continuous Profit ($)": round(prof_cont, 2),
                "Whole-Unit Sales": s_int,
                "Whole-Unit Profit ($)": round(prof_int, 2),
                "Status": feasible,
            })
        df_cand = pd.DataFrame(rows)
        st.dataframe(df_cand, use_container_width=True, hide_index=True)

        best_row = df_cand.loc[df_cand["Continuous Profit ($)"].idxmax()]
        st.success(
            f"**Optimal Constrained Price:** **${best_row['Price ($)']:.2f}** "
            f"(Continuous Profit: **${best_row['Continuous Profit ($)']:,.2f}** | "
            f"Whole-Unit Profit: **${best_row['Whole-Unit Profit ($)']:,.2f}** at {int(best_row['Whole-Unit Sales'])} packages)."
        )

    else:  # Advanced
        st.info(
            "**Advanced Task (Accumulation & Rate Modeling):** Evaluate an isolated 10-day promotional rate model "
            "$r(t) = 100 + 20t$ and $c(t) = 60 + 5t$ (dollars/day) over $0 \le t \le 10$ alongside constrained optimization."
        )
        t_end = st.slider("Integration Horizon T (days)", min_value=1, max_value=10, value=10)
        acc_rev = 100 * t_end + 10 * (t_end ** 2)
        acc_cost = 60 * t_end + 2.5 * (t_end ** 2)
        acc_prof = acc_rev - acc_cost
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Accumulated Revenue ∫r(t)dt [0,{t_end}]", f"${acc_rev:,.2f}")
        c2.metric(f"Accumulated Cost ∫c(t)dt [0,{t_end}]", f"${acc_cost:,.2f}")
        c3.metric(f"Net Accumulated Gain [0,{t_end}]", f"${acc_prof:,.2f}")
        st.caption("Note: This rate exercise models a short campaign window separately and does not overwrite the monthly ledger.")

    # Aligned Profit & Derivative Visuals
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=prices, y=profit_unconstrained, name="Unconstrained Profit P(p)", line=dict(dash="dash", color="#7f8c8d")))
    fig_p.add_trace(go.Scatter(x=prices, y=profit_constrained, name="Constrained Profit (Capped)", line=dict(color="#1f77b4", width=3)))
    fig_p.add_hline(y=0, line_dash="dot", line_color="black", annotation_text="Break-Even ($0)")
    if 0 <= p_corner <= p_max_domain:
        fig_p.add_vline(x=p_corner, line_dash="dash", line_color="#d95f02", annotation_text=f"Capacity Corner p=${p_corner:.2f}")
    fig_p.update_layout(
        title=f"Profit Function P(p) | Snapshot {state['snapshot_id']} (v{state['state_version']})",
        xaxis_title="Package Price p (USD)",
        yaxis_title="Monthly Profit (USD)",
        height=360,
    )
    st.plotly_chart(fig_p, use_container_width=True)

    fig_dp = go.Figure()
    fig_dp.add_trace(go.Scatter(x=prices, y=d_profit_constrained, name="Constrained Derivative P'(p)", line=dict(color="#2ca02c", width=2.5)))
    fig_dp.add_hline(y=0, line_dash="dot", line_color="black", annotation_text="P'(p) = 0")
    if 0 <= p_corner <= p_max_domain:
        fig_dp.add_vline(x=p_corner, line_dash="dash", line_color="#d95f02", annotation_text="Corner (P' undefined)")
    fig_dp.update_layout(
        title="Marginal Profit With Respect to Price: P'(p) (Units: $/month per $1 price increase)",
        xaxis_title="Package Price p (USD)",
        yaxis_title="Rate of Change P'(p)",
        height=300,
    )
    st.plotly_chart(fig_dp, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 3: LEDGER & SIMULATION RUN
# ------------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Approve & Advance Simulation Ledger")
    st.write(
        "Each approved monthly step records revenue and expenses into the permanent ledger and advances "
        "`state_version` by 1. Duplicate Run IDs are automatically blocked."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        run_id_input = st.text_input("Unique Run ID", value=f"RUN-2027-{state['state_version']:02d}")
    with c2:
        sim_date_input = st.text_input("Period End Date (YYYY-MM-DD)", value=state["simulation_date"])
    with c3:
        camp_id_input = st.text_input("Campaign ID (if Ad Spend > $0)", value="CAMP-001")

    if st.button("Approve & Record Simulation Month", type="primary"):
        ok, msg = record_simulation_step(
            state,
            run_id=run_id_input.strip(),
            sim_date=sim_date_input.strip(),
            metrics=preview,
            mode="Normal",
            campaign_id=camp_id_input.strip() if preview["marketing"] > 0 else None,
        )
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    st.divider()
    st.markdown("### Recorded Event Ledger")
    if state["ledger"]:
        df_ledger = pd.DataFrame(state["ledger"])
        st.dataframe(df_ledger, use_container_width=True, hide_index=True)
        csv_data = df_ledger.to_csv(index=False)
        st.download_button(
            "Export Ledger CSV",
            data=csv_data,
            file_name=f"{state['team_id']}_ledger_v{state['state_version']}.csv",
            mime="text/csv",
        )
    else:
        st.caption("No transactions recorded yet. Click 'Approve & Record Simulation Month' above to log Round 1.")

# ------------------------------------------------------------------------------
# TAB 4: MKT-3 ACCEPTANCE TESTS & FIXTURES
# ------------------------------------------------------------------------------
with tabs[3]:
    st.subheader("MKT-3 Automated Acceptance & Fixture Checks")
    st.write(
        "These tests verify your math engine against the exact expected numbers in the Career Venture Lab Handbook (Page 100)."
    )

    if st.button("Run All MKT-3 Acceptance Tests"):
        test_results = []

        # Test 1: Zero sales check
        t1_state = json.loads(json.dumps(DEFAULT_STATE))
        m_zero = compute_metrics(t1_state, requested_override=0)
        pass_t1 = (m_zero["gross_revenue"] == 0.0 and m_zero["variable_expense"] == 0.0 and m_zero["operating_profit"] == -900.0)
        test_results.append({
            "Test Name": "1. Zero Sales Check",
            "Expected": "Revenue $0, Variable $0, Profit -$900",
            "Actual": f"Revenue ${m_zero['gross_revenue']:.0f}, Variable ${m_zero['variable_expense']:.0f}, Profit ${m_zero['operating_profit']:.0f}",
            "Status": "PASS" if pass_t1 else "FAIL",
        })

        # Test 2: Demand exceeds capacity (12 requested, 10 capacity)
        t2_state = json.loads(json.dumps(DEFAULT_STATE))
        m_cap = compute_metrics(t2_state)
        pass_t2 = (m_cap["sold"] == 10 and m_cap["unserved_demand"] == 2 and m_cap["operating_profit"] == 800.0)
        test_results.append({
            "Test Name": "2. Demand Exceeds Capacity (Baseline)",
            "Expected": "Sold 10, Unserved 2, Profit $800",
            "Actual": f"Sold {m_cap['sold']}, Unserved {m_cap['unserved_demand']}, Profit ${m_cap['operating_profit']:.0f}",
            "Status": "PASS" if pass_t2 else "FAIL",
        })

        # Test 3: MKT-3 Revision Shock (extra revisions = 2 hrs/package)
        t3_state = json.loads(json.dumps(DEFAULT_STATE))
        t3_state["inputs"]["revision_hours_per_package"] = 2.0
        m_rev = compute_metrics(t3_state)
        pass_t3 = (
            m_rev["capacity"] == 8
            and m_rev["variable_per_unit"] == 90.0
            and m_rev["gross_revenue"] == 2000.0
            and m_rev["variable_expense"] == 720.0
            and m_rev["operating_profit"] == 380.0
        )
        test_results.append({
            "Test Name": "3. Revision Disruption (+2 hrs/pkg)",
            "Expected": "Cap 8, Unit Cost $90, Rev $2,000, Var $720, Profit $380",
            "Actual": f"Cap {m_rev['capacity']}, Unit Cost ${m_rev['variable_per_unit']:.0f}, Rev ${m_rev['gross_revenue']:,.0f}, Var ${m_rev['variable_expense']:.0f}, Profit ${m_rev['operating_profit']:.0f}",
            "Status": "PASS" if pass_t3 else "FAIL",
        })

        # Test 4: 3-Month Fixture Replay
        t4_state = json.loads(json.dumps(DEFAULT_STATE))
        fixture_rows_out = []
        for idx, row in MONTHLY_FIXTURE.iterrows():
            m_fix = compute_metrics(
                t4_state,
                requested_override=int(row["requested"]),
                capacity_override=int(row["capacity_override"]),
                ad_override=float(row["ad_cost"]),
            )
            record_simulation_step(
                t4_state,
                run_id=f"FIX-{row['month']}",
                sim_date=f"{row['month']}-28",
                metrics=m_fix,
                mode="Fixture",
                campaign_id="CAMP-FIX-FEB" if row["ad_cost"] > 0 else None,
            )
            fixture_rows_out.append((m_fix["sold"], m_fix["gross_revenue"], m_fix["total_operating_expense"], m_fix["operating_profit"], t4_state["cash"]))

        expected_fix = [
            (10, 2500.0, 1700.0, 800.0, 4800.0),
            (10, 2500.0, 1800.0, 700.0, 5500.0),
            (7, 1750.0, 1460.0, 290.0, 5790.0),
        ]
        pass_t4 = (fixture_rows_out == expected_fix)
        test_results.append({
            "Test Name": "4. 3-Month Fixture Replay (Jan-Mar 2027)",
            "Expected": "Closing Cash: $4,800 -> $5,500 -> $5,790",
            "Actual": f"Closing Cash: ${fixture_rows_out[0][4]:,.0f} -> ${fixture_rows_out[1][4]:,.0f} -> ${fixture_rows_out[2][4]:,.0f}",
            "Status": "PASS" if pass_t4 else "FAIL",
        })

        # Test 5: Duplicate Run Protection
        dup_ok, _ = record_simulation_step(
            t4_state,
            run_id="FIX-2027-01",
            sim_date="2027-01-28",
            metrics=m_cap,
            mode="Fixture",
        )
        test_results.append({
            "Test Name": "5. Duplicate Run Protection",
            "Expected": "Rejected (False)",
            "Actual": f"Rejected ({not dup_ok})",
            "Status": "PASS" if not dup_ok else "FAIL",
        })

        st.dataframe(pd.DataFrame(test_results), use_container_width=True, hide_index=True)

    with st.expander("View Reference Monthly Fixture (monthly_fixture.csv)"):
        st.dataframe(MONTHLY_FIXTURE, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
# TAB 5: STAGE 2-3 ROADMAP (HONEST UNIMPLEMENTED LIST)
# ------------------------------------------------------------------------------
with tabs[4]:
    st.subheader("Project Roadmap & Unimplemented Modules")
    st.markdown(
        """
        Per Career Venture Lab rules, modules are built and verified in stages:
        - **Stage 1 (Active Now):** Business inputs, AP Calculus optimization & derivative plots, dated event ledger, duplicate-run protection, Save/Load JSON, and MKT-3 acceptance tests.
        - **Stage 2 (Next):** Departmental AI handoff cards (Finance, Operations, Market/Marketing, Independent Reviewer), Report Center (Income Statement, Cash Flow, Balance Sheet, PDF/CSV export), and Costed Marketing Studio.
        - **Stage 3 (Planned):** Frozen-snapshot Practice Assessment generator and Cross-Course Connections panel.
        - **Stage 4 (Optional):** Demonstration storefront (no real money).
        """
    )
