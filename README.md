# GA4 BigQuery export data generator

This is the generator behind the **Superform Labs GA4 BigQuery Export Data
Generator**, the app at <https://datagenerator.ga4dataform.com>. The app
installs a fake Google Analytics 4 (GA4) BigQuery export in your own Google
Cloud project and refreshes it every morning. This repository is the code
that writes that data, so you can see how it works.

You do not need this repository to use the app. The app does everything for
you. Read on if you want to know what the numbers are made of, change them,
or run the generator yourself.

## What it simulates

A GA4 BigQuery export, the one Google writes when you link a GA4 property to
BigQuery. One table per day, named `events_YYYYMMDD`, one row per event:

- **31 top-level columns**, 217 field paths in all, the shape of a real web
  export: `event_date`, `event_timestamp`, `event_name`, the repeated
  `event_params`, `user_id` and `user_pseudo_id`, `privacy_info`,
  `user_properties`, `device`, `geo`, `traffic_source`,
  `collected_traffic_source`, `session_traffic_source_last_click`,
  `ecommerce`, the repeated `items`, and the rest.
- The column list is `src/ga4synth/data/events.json`, captured from a live
  GA4 export. Nobody edits it by hand. Every generated row is checked
  against it both ways: an unknown field fails, and a missing field fails.
- The day of a row is its day in the property's **reporting timezone**, not
  in UTC, as in a real export. A session that starts at 23:50 spills into
  the next day's table.
- Out of scope: `events_intraday_*`, `users_*` and `pseudonymous_users_*`.
  Only the daily event tables are produced.

The traffic is one website: **GA4Dataform's own, on `ga4dataform.com`**, as
an invented version of itself. All four configurations use that brand and
that hostname, with a home page, feature pages, a pricing page,
documentation, a blog, a plan catalogue and a sign-in.

So the brand is a real one, ours. Everything the data says about it is made
up: the pages, the plans and their prices, the campaigns, the sales seasons,
the search terms, the volume of traffic, and every visitor. No row describes
a real person, and no number here is a real number of GA4Dataform's. The
point of using our own brand is that the dataset reads like one coherent
company rather than a jumble of placeholders.

Two properties make the data worth querying rather than just worth looking
at:

- **It is deterministic.** The same configuration and the same date always
  give the same rows. Re-run a day a year later and you get the same bytes.
- **It holds together.** Sixteen checks run over a generated day before
  anything is loaded. A purchase has a `view_item` earlier in its session.
  Revenue equals the sum of the items. A visitor who refused analytics
  cookies carries no `user_pseudo_id` anywhere. See "How a day is built"
  below.

## The files

Everything sits at the root of this repository.

| Path | What it is |
|---|---|
| `src/ga4synth/` | The generator: 12 Python files, plus `data/events.json`, the export schema |
| `config/default/`, `config/ecommerce/`, `config/eu-consent/`, `config/lead-generation/` | The four configurations, one folder each, two files per folder |
| `pyproject.toml` | Builds the Python package `ga4synth` from `src/`, with its optional `bigquery` extra |
| `uv.lock` | The resolved lock file, so a clone installs the same versions |
| `Dockerfile` | How the generator is packaged for the daily refresh. See "Running it in a container" |
| `tests/` | The tests: the generator's own, and tests that drive its command line |
| `LICENSE` | The GNU General Public License, version 3. For the code |
| `LICENSE-DATA` | CC0 1.0. For the data the generator produces |
| `ORIGIN.md` | Where this code came from, and what changed at each step |

## The four configurations

A configuration is two YAML files in one folder:

| File | What it says | Examples of what is in it |
|---|---|---|
| `property.yaml` | **What exists.** The property and the website | hostname, brand, currency, reporting timezone, the page types and their paths, the plan catalogue with its prices, the channels and campaigns, the devices and countries, which events are tracked |
| `mixer.yaml` | **How much of it happens.** The traffic | new visitors a day, the weekly and seasonal shape, where a visit starts and where it goes next, scroll and click rates, how long a page is read, the purchase and lead rates, how many visitors return |

Split that way, you can change the volume of traffic without touching the
site, and change the site without touching the volume.

All four describe the **same website**, seen from a different angle. Each one
exercises a different part of a GA4 export:

| Folder | The same site, seen as | What it exercises |
|---|---|---|
| `default` | the marketing site, with no checkout | browsing: page views, sessions, scrolls, clicks, site search. No event of a shop, and `items` is empty on every row |
| `ecommerce` | the site selling its plans and add-ons online, in US dollars | the shop funnel, from `view_item_list` and `view_item` through `add_to_cart` and `begin_checkout` to `purchase`, with revenue and items |
| `eu-consent` | the site seen by European visitors, in euros with VAT, on Berlin time | consent mode: about 44% of the rows of a day are collected without analytics storage, so they carry no `user_pseudo_id` and no session id |
| `lead-generation` | the site with a form to book a demo, and no sign-in, on Chicago time | the lead funnel: `form_start`, `form_submit` on `/demo`, then `generate_lead` on `/demo/thank-you` |

`default` and `ecommerce` are one pair: `default` is `ecommerce` with the
shop switched off, and nothing else changed. Same seed, so the two hold the
same visitors, arriving at the same second from the same campaign. What
differs is what they do on the site. That is there on purpose: it lets you
compare a report with and without ecommerce on otherwise identical traffic.

Third-party sites keep their own names. The search engines and the social
networks that send the traffic are the real ones, and the review sites and
forums are made up, on `.example` addresses so that they cannot resolve. A
visitor also clicks out to a GA4Dataform page on a real social network. None
of what the data says about any of those sites, real or made up, describes
real traffic of theirs.

## How a day is built

From a configuration and a date to rows, in five steps.

1. **The visitors.** `mixer.yaml` says how many new visitors arrive on a
   given date. The weekday, the season and the calendar events of the
   configuration bend that number. Each new visitor belongs to the day they
   first arrived, and is identified by that day and their position in it.
2. **The visits.** A visitor who arrived earlier may come back. Whether they
   do on this date, how many sessions they have, and at what second each one
   starts, all follow from who they are and what date it is.
3. **The journey.** A session enters on a page type, chosen by the entry
   weights, then walks from page to page by the transition weights until it
   ends. Each page emits its events: a `page_view`, a `scroll` or a `click`
   if the dice say so, a funnel event if the page has one. The visitor's
   device, country, channel and campaign come with them.
4. **The rows.** Every abstract event becomes an export row, with its
   `event_params`, its `user_properties`, its nested records, its batch
   position, and its timestamp in microseconds. Rows whose day falls outside
   the date asked for are dropped, which is how a session crossing midnight
   lands in the right table.
5. **The checks.** `verify` runs them on a day. `publish` runs them on each
   day it is about to load, and refuses to load one that fails, so a broken
   day never reaches BigQuery.

**Why the same date gives the same rows.** The generator never calls a
random number generator in sequence. Every single choice is derived by
hashing a key that names the thing being decided: this visitor, this
session, this page, this date, plus the configuration's seed. So a decision
does not depend on how many decisions came before it, and generating one day
needs no other day and no stored state. Change the seed in `property.yaml`
and you get a different, equally stable world.

**What the checks look at.** `verify` runs the schema check and sixteen
invariants over the generated day, and stops with a non-zero exit code if
any of them fails. They are in `src/ga4synth/invariants.py`:

| Check | What it refuses |
|---|---|
| `check_shard_matches_event_date` | A row whose `event_date` is not the day of the table, or disagrees with its own timestamp |
| `check_identifier_stability` | One `user_pseudo_id` reporting two different first-touch timestamps, or an incoherent session |
| `check_user_id_stability` | One device reporting two `user_id` values, or reporting one on some of its events only |
| `check_server_side_events` | A consented row with no session id that is not a server-side purchase, or does not look like one |
| `check_consent_denied_rows` | A row collected without analytics storage that still carries an identifier |
| `check_timestamp_monotonicity` | A session where the batch order and the clock disagree |
| `check_first_batch_composition` | A first batch holding anything other than the page-load events of its session |
| `check_session_lifecycle` | A second `session_start` in one session, or a second `first_visit` for one visitor |
| `check_entrances` | The `entrances` parameter twice in a session, or on anything but a `page_view` |
| `check_funnel_nesting` | A funnel step without every earlier step in the same session: a `purchase` with no `begin_checkout`, `add_to_cart` or `view_item`, or a `generate_lead` with no `form_start` |
| `check_purchased_items_were_viewed` | An item bought that the visitor never looked at |
| `check_revenue_reconciles` | A purchase whose `purchase_revenue` is not the revenue of its items |
| `check_transaction_ids_unique` | The same order number on two purchases in one day |
| `check_null_policy` | A field filled that a web-only export always leaves empty |
| `check_session_engaged_slot` | `session_engaged` in the wrong value slot: an integer on `session_start`, a string elsewhere |
| `check_single_value_slot` | A parameter with none, or more than one, of its four value slots filled |

## Try it

You need [uv](https://docs.astral.sh/uv/). The package asks for Python 3.10
or newer, because the BigQuery client it loads with does. Ask uv for 3.12,
which is the version everything here is tested with, and it fetches that
version if your machine has another one. Run every command from the root of
your clone.

```sh
uv sync --python 3.12
```

That installs `ga4synth` from this folder, editable, with the `bigquery`
extra and pytest.

Every command names its configuration. There is no configuration at a
default path, so a command without one stops with exit code 2. The two
options go **before** the name of the command:

```sh
# Does a day hold together? The schema check plus the sixteen invariants.
# Exit code 0 means pass.
uv run ga4synth --property config/default/property.yaml --mixer config/default/mixer.yaml verify --date 2026-09-01

# What does a day look like? Rows, consent, users, sessions, purchases,
# revenue, then the count of every event and every channel.
uv run ga4synth --property config/ecommerce/property.yaml --mixer config/ecommerce/mixer.yaml summary --date 2026-09-01
```

`--scenario <name>` is the short way. It names a folder of `config/` and
replaces the two options, so you cannot pass both:

```sh
uv run ga4synth --scenario eu-consent summary --date 2026-09-01
uv run ga4synth --scenario lead-generation summary --date 2026-09-01
```

`summary` of `ecommerce` on 2026-09-01 starts like this, and prints the same
numbers on any machine:

```
shard events_20260901
  rows            24,760
  no consent      3,136 rows (12.7%)
  users           3,147
  sessions        3,796
  purchases       195
  revenue         69,706.00 USD
  conv. rate      4.40%
  AOV             357.47 USD
```

To see what would be loaded into BigQuery, without loading anything:

```sh
uv run ga4synth --scenario ecommerce publish --dataset example-project:analytics_770000001 --date 2026-09-01 --days 1 --dry-run
```

It prints one line per day and writes nothing:

```
[dry run] would load 24,760 rows into example-project.analytics_770000001.events_20260901

published 1 shard(s)
```

To write the rows to local files instead, use `generate`. It writes
`out/events_20260901.json.gz`, gzipped newline-delimited JSON, one row per
line:

```sh
uv run ga4synth --scenario ecommerce generate --date 2026-09-01 --out out
```

### The tests

They take about half an hour, because several of them generate whole days:

```sh
uv run pytest
```

Everything passes from this clone alone, with **one test skipped**. That one
compares the export schema with a written specification that is kept with the
app and is not published here, so there is nothing to compare against. It says
so rather than failing:

```
SKIPPED [1] docs/contracts/ is not part of this repository, so there is no ga4-export-schema.md to check against
```

The columns are still checked here. The schema itself,
`src/ga4synth/data/events.json`, is part of the package, and the other test in
that file reads it and checks that every generated row carries exactly those
columns, for `default` and for `ecommerce`.

No test reads the network or needs any credential, and none asserts a number
of rows or a rate, so turning a traffic dial in `mixer.yaml` does not break
them.

### Two commands write to BigQuery

Say it plainly: **`load`, and `publish` without `--dry-run`, write into a
BigQuery dataset in a real Google Cloud project.** They use your
Application Default Credentials and they replace the day table they write
(`WRITE_TRUNCATE`), so a table of the same name loses what it held. They
need the optional `bigquery` extra. `uv sync --python 3.12` installs it, and
the plain pip way, from the root of your clone, is `pip install '.[bigquery]'`,
which is what the `Dockerfile` runs. There is no release of this package on
PyPI, so install it from the clone and not by name.

They never create the dataset. You create it yourself, which is also a way
of saying that the generator cannot write anywhere you have not prepared on
purpose.

Every other command is local and reads nothing from the network. `--dry-run`
on `load` and on `publish` does all the work and skips the write.

The full command line:

| Command | What it does |
|---|---|
| `generate --date --out` | Writes one day to `<out>/events_YYYYMMDD.json.gz` |
| `verify --date` | Generates a day in memory and runs the schema check and the invariants. Exit 1 on failure |
| `summary --date` | Prints the shape of a day |
| `backfill --from --to --out --verify` | Writes one file per day in a range |
| `load --date --out --dataset --location --dry-run` | Loads a day already generated into `events_YYYYMMDD` |
| `publish --dataset --date --days --location --workers --dry-run` | Generates, verifies and loads the last N days. Refuses to load a day that fails verification |

Exit codes: `0` success; `1` a failed check, a failed load, or a shard file
that does not exist; `2` a configuration that is missing or unreadable.

## Running it in a container

The `Dockerfile` is how the generator is packaged for the daily refresh an
install gets. It installs the package and the four configurations, and its
entrypoint is `ga4synth` with `publish`. The image is built by tooling that
belongs to the app and is not in this repository, so the file is here to be
read rather than to be a supported product. Build it yourself if it suits
you, or run the generator any other way. Nothing about the generator depends
on it.

## Two licences

The code and the data it writes are different things, so they carry
different licences.

**The code is under the GNU General Public License, version 3 or later**
(`LICENSE`, the GPL's own text, verbatim). You may use it, study it, change
it and pass it on. If you distribute it, or a changed version of it, you
pass on the same freedoms and the source along with it.

```
Copyright (C) 2026 Superform Labs OÜ

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option)
any later version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
more details.

You should have received a copy of the GNU General Public License along
with this program.  If not, see <https://www.gnu.org/licenses/>.
```

**The data is CC0 1.0** (`LICENSE-DATA`): the public domain. Any dataset
this generator produces, including the one the app installs in your own
Google Cloud project, is yours to copy, change, publish, teach with and sell,
with no permission and no attribution. The rows are entirely made up: they
are not derived from any real person's behaviour, and not from GA4Dataform's
real analytics either.

The two are independent. The GPL covers the generator. It does not reach the
rows the generator writes.

## Found a bug?

Please tell us. Open an issue with the bug form:

<https://github.com/superformlabs/GA4-BigQuery-export-data-generator/issues/new?template=bug-report.yml>

A good report says what you ran, what you expected and what happened. Paste
the command and the output. Please leave out anything private: an issue is
public, so no project ID, no dataset name and no customer data.

**Pull requests are off.** We read every issue and make the change here
ourselves. You are free to fork this repository and take it where you like;
the licence is there for exactly that.

Anything private, including a security problem, goes to
**support@superformlabs.eu** instead of an issue.
