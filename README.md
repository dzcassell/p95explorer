# P95 Explorer

A local bandwidth planning lab for Cato Networks tenants. Compare fixed site licenses, enforced bandwidth pools, and the documented January 2027 bursting model. Experiment with growth, headroom, site allocations and regional capacity, and see how P95 changes when a spike lasts longer.

**Independent planning software.** Recommendations describe capacity under the selected model; they are not quotes or a substitute for your agreement or CMA usage reports.

## Run with Docker

```sh
git clone https://github.com/dzcassell/p95explorer.git
cd p95explorer
docker compose up --build -d
```

Open **http://localhost:8080** and choose **Load demo**. The demo generates a complete, synthetic prior month across six sites and three regions. No API key is needed.

Docker Desktop works on Windows and macOS; Linux needs Docker Engine with Compose. Use Linux containers on Windows. The image supports `linux/amd64` and `linux/arm64`; CI builds both. The server uses Python's standard library, SQLite, and local browser assets, with no runtime package downloads or CDN dependencies.

Stop with `docker compose down`. The named `explorer-data` volume retains observations and scenario settings. Back up this volume before deleting it. The service binds to the host's loopback address: this version is designed for a single local operator.

## Connect to Cato

1. Generate a **read-only** API key in CMA. A viewer service principal is suitable for an automated collector.
2. Choose **Connect tenant**, enter the account ID, key and appropriate API endpoint, then **Discover sites**.
3. Select the physical/cloud sites you want to analyze; exclude VPN users. Collect a month. Current-month collection stops at the last completed UTC day.
4. Assign each site's verified license region and current bandwidth limit. These are scenario inputs, not automatically detected licenses. Save the scenario to preserve your mapping.

Credentials entered in the app are held in memory for the request/collection and are not persisted or returned. Alternatively, copy `.env.example` to `.env` and fill in `CATO_ACCOUNT_ID`, `CATO_API_KEY`, and `CATO_API_ENDPOINT`. Compose reads `.env`; direct Python execution uses process environment variables. `.env` is excluded from Git and the Docker build. Protect it as a credential file. Environment credentials persist wherever you manage Docker configuration.

CMA instances with a regional prefix may require a corresponding API host (for example `cc.us1.catonetworks.com` → `api.us1.catonetworks.com`). Only Cato HTTPS GraphQL endpoints are accepted, and redirects are disabled.

Collection runs in the background, saves completed batches locally, and upserts repeated buckets. You can recollect the same month safely. A failed batch retains previous results; restarting the container interrupts an active job, so restart collection afterward. Switch back to demo with **Load demo**. Observations are isolated by tenant ID.

## Models and interpretation

| Model | Comparison |
|---|---|
| Bursting pool · January 2027 | Highest daily regional sum of site daily P95s, using the October 4, 2026 documentation profile |
| Enforced bandwidth pool | Site allocation totals against pool capacity; observed site peaks against individual limits |
| Fixed site licensing | Observed site peaks against each fixed site capacity |
| Classic monthly P95 | Educational monthly per-site percentile comparison; not a Cato bursting billing rule |

Growth scales observed rates. Headroom increases recommended capacity, rounded up to 10 Mbps as a planning increment—not an assertion about purchasable SKUs. Pools remain separate by region. Cloud Interconnect and stand-alone country enforcement exceptions are highlighted. Pricing, overage charges, service add-ons, and SKU availability must come from your commercial agreement.

The app displays coverage against the entire calendar month. Incomplete observations produce provisional results. Null or missing directional buckets are excluded, not fabricated as zero. Already enforced traffic can conceal demand beyond a license limit. The API may return zero-valued buckets for unavailable telemetry; zero alone does not prove a site was idle. Compare with CMA before making purchasing decisions.

## CSV interchange

Import/export normalized **five-minute peak Mbps** data:

```csv
site_id,name,region,timestamp,up_mbps,down_mbps
123,Example Branch,Group 1,2026-09-01T00:00:00Z,25.4,81.2
```

Timestamps must be timezone-aware and aligned to UTC five-minute boundaries. Use numeric site IDs and one of `Group 1`, `Group 2`, `China`, `Vietnam`, `Morocco`, or `Unassigned`. Do not import average throughput and expect a peak-based licensing estimate. Duplicate buckets in one import are rejected. Imports use the separate `imported` workspace; repeated imports update matching site/time buckets. Keep files below 10 MB.

## Development

```sh
python3 -m app.server
python3 -m unittest discover -s tests -v
node --check app/static/app.js
```

Python 3.9+ runs the application locally; the Docker image uses Python 3.12. `P95_DATA_DIR`, `P95_PORT`, and `P95_BIND` configure local storage and binding. Tests use isolated temporary databases. GitHub Actions validates analytics, HTTP/CSV behavior, JavaScript syntax, Compose, image startup and both CPU architectures.

See [research and implementation notes](docs/cato-research.md) for sources and API assumptions. Live tenant testing is still required: the initial implementation is validated with synthetic data and API fixtures, not a tenant credential.
