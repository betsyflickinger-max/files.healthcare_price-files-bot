# price-files-bot

**The data engine behind [The Healthcare Files](https://files.healthcare): the receipt for the U.S. healthcare system.**

Federal rules now require hospitals to post their prices and require insurers and employer health plans to publish the rates they've negotiated with doctors and hospitals. That makes the last black box in American healthcare public on paper. In practice, the files are enormous (a single insurer file can run to hundreds of gigabytes), often broken, and almost impossible for a normal person to open.

This bot does the unglamorous part. Every day it finds, downloads, checks and reads those files, keeps an untouched copy of every original, and flags the ones that are missing or broken. The Healthcare Files turns the result into something anyone can search: what a procedure costs, at which provider, under which insurance network, compared with what Medicare pays.

> The site is in private preview while it's being built and tested. It will open to the public at **files.healthcare**.

## What it collects

- **Hospital price files.** Every hospital on CMS's Hospital General Information list (VA and Defense Department hospitals excluded), checked about once a week, with broken links retried daily.
- **Insurer and health plan rate files** (the Transparency in Coverage "in-network" files), read on rented cloud machines when they change. The coverage expands state by state.
- **What's missing.** Hospitals and insurers with no usable file are tracked by name, along with what was tried and when. That list feeds the site's *Price File Watch*.

## The rules

1. **Every price comes from a real source** (a hospital file, an insurer file or a provider's posted price) and links back to it.
2. **Nothing is estimated or averaged.**
3. **Every price shows when it was checked**, and old data is flagged.
4. **Nothing is deleted.** Every version of every file is kept compressed and unchanged, and copies go to the [Internet Archive](https://archive.org), so any price can be traced back to the exact file and row it came from. This also builds a record of how prices change over time.
5. **High prices stay visible.** Outliers are labeled, never filtered out, because real overcharges are part of the story.

## Why

This project was started by a former employee-benefits consultant who spent years watching, from the inside, how negotiated prices stay hidden from the people paying the bills. It's self-funded and run without profit. Nobody can pay to change a rate.

## Found a missing or broken file?

If you know where a hospital or insurer posts a file we couldn't find, please [open an issue](https://github.com/betsyflickinger-max/price-files-bot/issues/new) with the link. Corrections are welcome too.

## For developers

- How the bot runs, what it stores and how to set it up: [docs/operations.md](docs/operations.md)
- The hospital file reader: [`bot/reader.py`](bot/reader.py)
- The insurer file pipeline: [`insurers/`](insurers/)

Change-detection ideas adapted from [hospital-price-history](https://github.com/lkowalcz/hospital-price-history) (CC0). Thanks to everyone else working to make these files readable.

## License

The bot's code is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0). You're free to use, study, change and share it. If you run a modified version, including as a website or service, you must publish your changes under the same license.

Copyright © 2026 Mary Elizabeth (Betsy) Flickinger. For other licensing arrangements, [open an issue](https://github.com/betsyflickinger-max/price-files-bot/issues/new).

This license covers the code in this repository. The price data comes from files hospitals and insurers are required to publish.
