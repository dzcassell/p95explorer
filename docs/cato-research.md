# Cato source notes

Reviewed October 8, 2026. Public guidance may change; keep the calculation profile versioned and reconcile it with CMA.

## Licensing sources

- [Usage Measurement](https://knowledge.catonetworks.com/docs/usage-measurement), updated October 4, 2026: the bursting pool evaluates the higher direction of aggregated site traffic, daily site P95, then the maximum daily regional aggregate in a calendar month. Regions cannot offset one another. Cloud Interconnect and stand-alone country enforcement exceptions apply. Commercial terms define true-up/true-forward pricing. The app intentionally excludes monetary estimates.
- [Bursting Model License](https://knowledge.catonetworks.com/docs/jan-2027-license-bursting-model): identifies January 2027 applicability and the broader product layers. This app models bandwidth capacity only.
- [Managing Site Bandwidth](https://knowledge.catonetworks.com/docs/managing-site-bandwidth-in-licenses): legacy enforcement distinguishes fixed sites from geographically scoped pools of site allocations; a site capacity applies independently to each traffic direction across active links. Legacy pooled licensing is not supported in non-tiered country regions. The app does not assume every model is available to every site.
- [Identifying your License Model](https://knowledge.catonetworks.com/docs/identifying-your-license-model): users should verify the account's actual model in CMA.

Earlier indexed usage guidance described discarding the largest daily regional aggregate. That differs from the October 4 page. The implemented `bursting-2027` profile uses the newer maximum-day rule; a generic monthly percentile remains a separately labeled educational comparison. No undocumented price schedule is embedded.

## API sources

- [Example Site Bandwidth](https://knowledge.catonetworks.com/docs/example-site-bandwidth-with-accountmetrics-api): request grouped `bytesUpstreamMax` and `bytesDownstreamMax`. Peak values are bytes **per second**, even if units say `bytes`; convert to decimal Mbps by multiplying by 8 / 1,000,000 without dividing by bucket duration. The example's numeric timestamps are milliseconds, corroborated by the Timeseries reference; its prose calls them nanoseconds inconsistently.
- [Timeseries](https://knowledge.catonetworks.com/docs/cato-api-accountmetrics-timeseries): timestamp/value tuples; maximum 1,000 buckets per query.
- [AccountMetrics](https://knowledge.catonetworks.com/docs/cato-api-accountmetrics): explicit account ID and timeframe, grouped devices/interfaces, and fewer than 100,000 returned metric items.
- [Sites](https://knowledge.catonetworks.com/docs/cato-api-accountmetrics-sites) and [SiteInfo](https://knowledge.catonetworks.com/docs/cato-api-accountmetrics-sites-siteinfo): discovery supplies IDs, names, countries and connection types. Unfiltered metrics can include remote users; the collector requires explicit user-selected site IDs. PoP regions are not automatically treated as license groups.
- [Granularity](https://knowledge.catonetworks.com/docs/working-with-accountmetrics-granularity): the requested interval and bucket count determine granularity; the app rejects responses that do not return 300-second buckets.
- [Rate limiting](https://knowledge.catonetworks.com/docs/understanding-cato-api-rate-limiting): accountMetrics has a documented 15/minute allowance shared across keys for an account. Collection spaces requests by 4.2 seconds and retries rate-limit/transient failures. Other tools using the same tenant may still consume the allowance.
- [API connection](https://knowledge.catonetworks.com/docs/connecting-to-the-cato-api-from-the-graphql-playground) and [API keys](https://knowledge.catonetworks.com/docs/generating-api-keys-for-the-cato-api): regional endpoints and `x-api-key` authentication with read-only permissions.

## Collection contract

Daily UTC windows request 288 buckets and two peak labels, for batches of at most 100 sites: 57,600 items. Each query uses `groupDevices:true` and `groupInterfaces:true`. The client requires one grouped interface result per site; summing independent interface peak values could inflate throughput. Both directional values must exist for a bucket to be stored. Each persisted bucket has a unique tenant/site/timestamp key.

Site license regions and capacities are manually verified inputs. The app does not retrieve commercial license inventory, mutate tenant settings, collect pricing, or infer exact country group assignments. SQLite keeps normalized observations; it does not keep API keys.

## Validation boundary

Unit tests cover the 70/75-minute percentile transition, order of site/regional aggregation, maximum-day monthly selection, regional separation, missing-data coverage, growth/headroom, peak unit conversion, invalid inputs and grouped-interface rejection. HTTP tests cover CSRF/host protection, demo generation, scenario persistence, CSV validation and export.

A live acceptance run should verify the deployed GraphQL schema, selected site inventory, data retention/granularity for the requested historical period, grouped peak behavior and alignment with a complete CMA usage report. The current implementation cannot certify exact invoiced usage without that comparison.
