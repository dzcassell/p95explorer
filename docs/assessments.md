# Build a defensible bandwidth assessment

This workflow serves three audiences: an Account Executive can compare commercial options and share the executive report; a Sales Engineer can inspect calculations and constraints; a customer can check assumptions, growth plans and the evidence behind the recommendation.

## 1. Establish the baseline

Collect several complete months with **Connect tenant → From month / Through month**, or import peak-based observations. The collector supports up to 12 months per job, subject to Cato's available historical granularity. Analysis can select up to 24 stored months.

For each site, verify its license region, connection type and current allocation. Mark **Confirmed** when you have checked those inputs. For a Socket/IPsec site with optional per-site enforcement configured, mark **Optional enforcement**. Cloud Interconnect and stand-alone country enforcement are handled automatically. Confirm the current or proposed licensing model in the sandbox. Live data starts without assumed site/pool capacities; existing upgraded workspaces keep their values but require confirmation.

Recommendations are withheld if any selected month's observations are incomplete, the inventory/model is unverified, a region is ineligible for the model, or supplied CMA evidence materially disagrees with the result. Observed peaks and coverage remain visible. Only complete 288-bucket site days enter daily regional P95 aggregation. Nothing fills missing days with zero. Site connection types must identify supported Socket/vSocket, IPsec or Cloud Interconnect sites; remote user entries cannot become eligible bandwidth sites by checking a confirmation box.

An observed month can still hide unmet demand when existing enforcement shapes traffic. Complete telemetry is evidence of observed utilization, not proof that applications never needed more capacity. Site lifecycle changes can leave incomplete site/month coverage; select a fully observed window rather than assuming missing days were idle.

## 2. Explain the requirement

Use **Explain this number** on a regional card. It shows complete daily aggregates and the determining day. Inspect a site's discarded buckets to see the highest 14 samples excluded from a full day's 288 buckets, the remaining P95 cutoff, and their UTC timestamps.

The bursting profile uses the largest daily regional sum. Fixed sites use observed peaks; legacy pools must fit site allocations and appropriate site limits. Country pool planning must also cover the sum of recommended fixed site limits, even if its measured P95 is lower. Classic monthly P95 remains educational and cannot generate a final Cato recommendation.

**Compare with CMA** accepts manually supplied regional bandwidth values for the selected month. Reconciliation runs on complete bursting observations with zero global/region/site growth. A difference above the greater of 0.5 Mbps or 1% of the supplied CMA value withholds sizing until resolved. This tolerance is a tool setting in the calculation profile, not a published Cato billing tolerance. Entered values are labeled as supplied CMA evidence, not independently retrieved or certified reports.

## 3. Compare named options

Give the working scenario a meaningful name, such as “Current footprint,” “Renewal with 20% headroom,” or “New branches.” Set capacity, growth and headroom, then choose **Save as named option**. Up to 12 named options can be saved. Load an option using the saved-scenario selector; use **Update selected named option** to revise it.

In **Look beyond one month**, choose a common observation window. Check up to four saved options and choose **Compare saved options**. Each comparison uses those saved inputs over the same selected window. The regional summary shows its largest eligible planning requirement, determining month, and months above confirmed capacity. No regional surplus is transferred to a different region.

**Save working scenario** persists your current draft and verified site mapping. Named snapshots remain separate from that draft. Export CSV reflects the saved site mapping; assessment export captures the current draft before exporting.

## 4. Model growth and new sites

Global growth is a one-time uplift of the historical observations. Regional growth overrides global growth; a site-specific growth value overrides both. Leave an override empty to inherit the broader setting.

The forecast uses the largest historical regional demand. Fixed site forecasts size each site independently from its largest historical peak. Monthly growth compounds during the forecast horizon only. The horizon starts after the latest selected observation month; bursting projections start no earlier than January 2027. This is a deterministic scenario, not a statistical prediction or assurance about future usage.

Enter a planned site's name, region, start month, peak Mbps and daily P95 Mbps. It enters forecast months on/after its start date. Its P95 budget contributes to bursting measurement; its peak contributes to fixed site sizing. Country site budgets also set a fixed limit requirement. Proposed site values are user-entered assumptions, not API observations, and their available service/SKU must be checked commercially. P95 cannot exceed the entered peak.

## 5. Price the proposed options

Expand **Growth and commercial assumptions**. Enter a currency label, remaining term/projection months, any related-service flat monthly cost and one-time expansion fee. Use either regional monthly rates per Mbps or a verified SKU catalog. Enter excess rates where the agreement permits them, and confirm the pricing assumptions.

An optional catalog uses this structure (illustrative values only):

```json
{
  "Group 1": [
    {"sku": "Example 500 Mbps", "capacity": 500, "monthly": 1000},
    {"sku": "Example 1 Gbps", "capacity": 1000, "monthly": 1800}
  ]
}
```

A catalog overrides linear unit rates for that region. The lowest-priced supplied SKU meeting the requirement is selected. A fixed site scenario selects a tier independently per site; a pooled scenario selects per region. Catalog entries do not establish product/model eligibility, which must be verified from your agreement. If no supplied tier covers the required capacity, pricing is withheld. Other regions still need their own prices.

The bandwidth/excess discount applies to those charges; it does not discount flat service fees or the one-time expansion fee. The currency is a label, with no exchange-rate conversion. Tax is not calculated.

The comparison includes:

- **Adjust capacity monthly:** an illustrative cost of sizing each forecast month; your agreement may not allow monthly reductions or changes.
- **One term-sized expansion:** capacity sized to the whole horizon, retaining at least existing capacity, plus the supplied expansion fee. It does not assume a true-forward can reduce an existing license.
- **Current capacity + excess:** available only for bursting scenarios with current capacities and excess rates supplied, and where existing enforced site limits can support the projected traffic. Paying excess charges does not bypass a site bandwidth limit. Historical charges are outside the projection.

Flat costs can represent related security/insight services, but the app does not automatically calculate their licensing entitlements. Customer-specific terms, SKU availability, discounts and prices remain user-supplied. These are modeled options, not official Cato quotes.

## 6. Share or move the assessment

**Executive PDF** generates a summary plus technical appendix locally. It includes the observation window, model/profile, regional recommendations, commercial assumptions, site coverage/provenance, determining-day contributions, planned sites, and forecast. A report with unresolved evidence clearly withholds recommendations. Demo reports identify their observations as synthetic.

**Export assessment** downloads normalized observations, inventory, the working scenario, selected months, named options, CMA inputs and pricing assumptions as JSON. API keys and environment credentials are never serialized. This file still contains customer telemetry and commercially sensitive inputs: handle it as a customer assessment.

**Restore assessment** validates the file and creates a new isolated workspace. Existing tenants are not overwritten. Source labels identify imported observations, and matching rule profiles are required. The portable limit is 600,000 buckets and a file below 60 MB; use per-month CSV exports or a full Docker volume backup for larger datasets.

A portfolio or renewal decision still requires live API/CMA reconciliation and review of the customer's applicable licensing model and agreement. The app makes the assumptions inspectable; it cannot certify invoice accuracy from public documentation alone.
