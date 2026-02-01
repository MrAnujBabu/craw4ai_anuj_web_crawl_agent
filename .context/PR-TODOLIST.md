# PR Review Todolist

> Last updated: 2026-02-01 | Total open PRs: 85

---

## Solid Bug Fixes

| PR | Author | Description | Status |
|----|--------|-------------|--------|
| ~~#1746~~ | ~~ChiragBellara~~ | ~~Fix: sitemap-only seeding was initializing Common Crawl unnecessarily~~ | **merged** |
| ~~#1721~~ | ~~YuriNachos~~ | ~~Fix `<base>` tag ignored in html2text — relative links resolve wrong. (#1680)~~ | **merged** |
| ~~#1720~~ | ~~YuriNachos~~ | ~~Fix LLM schema generation fails when LLM wraps JSON in markdown code blocks. (#1663)~~ | **closed (already fixed)** |
| ~~#1719~~ | ~~YuriNachos~~ | ~~Fix GoogleSearchCrawler `script.js` missing from package distribution. (#1711)~~ | **merged** |
| ~~#1717~~ | ~~YuriNachos~~ | ~~Fix local sentence-transformers embeddings blocked by OpenAI fallback. (#1658)~~ | **merged** |
| ~~#1714~~ | ~~YuriNachos~~ | ~~Fix: Replace `tf-playwright-stealth` with `playwright-stealth` dependency. (#1553)~~ | **merged** |
| #1667 | christian-oudard | Fix `crwl --deep-crawl` only outputting first page. Real CLI bug with tests. | pending |
| #1640 | Martichou | Fix memory leak — unused browser contexts never cleaned up under continuous load. (#943) | pending |
| #1622 | zhaoyun006 | Fix redirect target verification in AsyncUrlSeeder and enhance tests. | pending |
| #1592 | jzmiller1 | Fix CDP page leaks and race conditions in concurrent crawling. (#1563) | pending |
| #1572 | yuexuan-chen | Fix CDP setting with managed browser. | pending |
| #1450 | prlz77 | Fix LLM extraction fails when content is in alternative response fields. | pending |
| #1364 | nnxiong | Fix `<script>` tag removal losing adjacent text in `cleaned_html`. | pending |
| #1308 | cjh-GITHUB | Fix css_selector variable type error (assigned to list). | pending |
| #1296 | vladmandic | Fix `VersionManager` ignoring `CRAWL4_AI_BASE_DIRECTORY` env var. 1-line fix. | pending |
| #1281 | garyluky | Fix proxy auth `ERR_INVALID_AUTH_CREDENTIALS`. Fixes #993, #974, #1109. | pending |
| #1234 | hellokayas | Fix TypeError when `keep_data_attributes=False` by ensuring list concat. | pending |
| #1211 | zhangbo-tj | Fix: safely create new page if no page exists in persistent context. | pending |
| #1207 | ninjapanzer | Fix streaming error handling. | pending |
| #1200 | Gyscos | Bugfix browser manager session handling. | pending |
| #1179 | Nuo-55 | Fix leak token when input url as raw html. | pending |
| #1150 | scris | Fix LLM extraction `response` variable not overridden causing `'str' has no attribute 'choices'`. | pending |
| #1133 | Daniel21b | Enforce auth when JWT is enabled. 1-line fix. | pending |
| #1106 | ruoyuGao | Fix: Adapt to CrawlerMonitor constructor change. | pending |
| #1081 | Joorrit | Fix deep crawl scorer logic was inverted — high-distance paths scored higher. | pending |
| #1077 | RoyLeviLangware | Fix bs4 deprecation warning (`text` -> `string`). 1 line. | pending |
| #1073 | saipavanmeruga7797 | Fix local HTML file crawling broken when `capture_console_messages=False`. | pending |
| #1065 | dzhao-gearset | Fix: Update deprecated Groq models to recommended replacements. | pending |
| #1059 | wangs1024 | Fix wrong proxy config type in proxy demo example. | pending |
| #1058 | Aaron2516 | Fix dict-type `proxy_config` not handled properly. (#1057) | pending |

## Good Features

| PR | Author | Description | Status |
|----|--------|-------------|--------|
| #1730 | hoi | Add configurable TTL for Redis task data. Prevents unbounded memory growth. | pending |
| #1729 | hoi | Add support for external Redis with embedded Redis disable option. | pending |
| #1707 | dillonledoux | Add `Crawl-delay` directive support from robots.txt. Good compliance feature. | pending |
| #1706 | vikas-gits-good | Fix `arun_many` not working with `DeepCrawlStrategy`. (#1277) | pending |
| #1702 | YxmMyth | Add CSS background image extraction. (#1691) | pending |
| #1689 | dillonledoux | Docker: optimize concurrency performance and memory management. | pending |
| #1683 | unknown | Implement double config for AdaptiveCrawler. | pending |
| #1674 | blentz | Add output pagination/control for MCP endpoints. Useful for LLM context windows. | pending |
| #1668 | microHoffman | Add `--json-ensure-ascii` CLI flag for Unicode handling. Clean, small. | pending |
| #1650 | sathyanarays | Add support for Vertex AI in LLM Extraction Strategy. | pending |
| #1580 | GrumpyLion | Add Azure OpenAI configuration support to crwl config. | pending |
| #1463 | TristanDonze | Add configurable `device_scale_factor` for screenshot quality. 3 files, clean. | pending |
| #1450 | prlz77 | Fix LLM extraction fails with alternative response fields. | pending |
| #1435 | charlaie | Add `redirected_status_code` to CrawlResult. 3 files, clean. | pending |
| #1425 | Nisarg38 | Add OpenRouter API support. | pending |
| #1417 | NickMandylas | Add CDP headers support for remote browser auth (AWS Bedrock etc). | pending |
| #1290 | 130347665 | Support type-list pipeline in JsonElementExtraction (multi-step extract). | pending |
| #1255 | itsskofficial | Fix JsonCssSelector to handle adjacent sibling CSS selectors (`+ tr`). | pending |
| #1238 | IgorLeno | Fix ManagedBrowser constructor and Windows encoding issues. | pending |
| #1220 | chineidu | Allow `OPENAI_BASE_URL` to be used to control the base_url for the LLM. | pending |
| #1180 | aravindkarnam | Add CallbackURLFilter for custom URL filtering in deep crawling. | pending |
| #999 | Morriz | Add filters that filter based on regular expressions in deep crawling. | pending |

## Quick Doc/Maintenance Merges

| PR | Author | Description | Status |
|----|--------|-------------|--------|
| #1734 | pgoslatara | Update outdated GitHub Actions versions (v4->v6). 2 files. | pending |
| #1716 | YuriNachos | Fix wrong return types in arun/arun_many docs. | pending |
| #1715 | YuriNachos | Add missing `CacheMode` import in quickstart docs. | pending |
| #1722 | YuriNachos | Add missing docstring to MCP `md` endpoint. | pending |
| #1655 | unknown | Replace Chinese comment with English in nullcontext method. 1 line. | pending |
| #1494 | AkosLukacs | Fix wrong param name in `arun()` docstring. | pending |
| #1488 | AkosLukacs | Fix syntax error in README JSON example. | pending |
| #1483 | unknown | Update README.md with latest docker image. | pending |
| #1416 | unknown | Fix missing bracket in README code block. | pending |
| #1272 | unknown | Fix get title bug in amazon example. | pending |
| #1263 | unknown | Fix: consistent with sdk behavior. | pending |
| #1225 | unknown | Fix docker deployment guide URL. | pending |
| #1223 | unknown | Docs: add links to other language versions of README. | pending |
| #1159 | lbeziaud | Fix cleanup warning when no process on debug port. 1 line. | pending |
| #1098 | unknown | Docs: fix outdated links to Docker guide and release notes. | pending |
| #1093 | unknown | Docs: Fixed incorrect elapsed calculation and output format. | pending |

## Duplicates (Close These)

| PR | Duplicate Of | Description |
|----|-------------|-------------|
| ~~#1703~~ | ~~#1721~~ | ~~Same `<base>` tag fix~~ **closed** |
| ~~#1698~~ | ~~#1721~~ | ~~Same `<base>` tag fix~~ **closed** |
| ~~#1697~~ | ~~#1717~~ | ~~Same embeddings fallback fix~~ **closed** |
| #1696 | #1722 | Same MCP docstring fix |
| ~~#1710~~ | ~~#1719~~ | ~~Same script.js packaging fix~~ **closed** |
| #1478 | #1715 | Same quickstart CacheMode fix |
| #1465 | #1715 | Same quickstart example fix |

## Skip / Close

| PR | Author | Why |
|----|--------|-----|
| #1600 | cbwinslow | "ASDF" — 10,644 additions, 39 files, no description. Accidental dump. |
| #1569 | Ahmed-Tawfik94 | 17,425 additions, 50 files, unsolicited massive Docker feature dump. |
| #1630 | Daniel21b | 4,637 additions, unsolicited enterprise JWT auth system. |
| #1700 | chansearrington | Claude Code as LLM provider — 1,457 additions, 17 files. Too large/niche. |
| #1525 | leoric-crown | MCP transport rewrite — 5,978 additions, 38 files. Massive refactor. |
| #1565 | TrungLee2020 | Vietnamese real estate crawler scripts, not core. |
| #1100 | xerexesx | "Add files via upload" — 0 changes, empty. |
| #1110 | lwsinclair | "Add MseeP.ai badge" — marketing badge spam. |
| #1724 | git-pranavbabu | PR title is the entire template. 1 trivial verbose param change. |
| #1547 | mziv | lxml update — touches 100 files (lockfile). Needs careful review. |
| #1395 | granolacowboy | "Feature/interactive wizard" — no description. |
| #1408 | PATAKAMURIVENKATAGANESH | "Basic Health Check Endpoint" — no description filled. |
| #1533 | unknown | Add Claude Code GitHub Workflow — CI workflow, not core. |
| #1274 | unknown | Devcontainer support — 913 additions, dev tooling. |
| #1420 | unknown | Opt-in telemetry system — 3,208 additions. Too large/sensitive. |
| #1497 | unknown | Firecrawl backend support — 191 additions, niche integration. |
| #1496 | unknown | normalize_url refactor — 869 additions, too large for URL normalization. |
| #1518 | unknown | Docker PDF strategy — 324 additions, Docker-specific. |
| #1413 | unknown | Full scan update — 290 additions, unclear scope. |
| #1373 | unknown | MCP server endpoint fixes — 753 additions, large. |
| #1212 | unknown | Stateless streamable_http transport for MCP — 154 additions. |
| #1157 | unknown | Content change detection — 229 additions, feature scope unclear. |
| #1140 | unknown | Prompt-driven recursive crawler script — 268 additions, not core. |
| #1124 | unknown | VNC streaming support — 98 additions, niche. |
| #1068 | unknown | Playground enhancement — 158 additions, separate feature. |
| #1083 | unknown | Provider base url feature — 40 additions, overlaps with #1220. |

---

## Resolved This Session

| PR | Author | Description | Merged Date |
|----|--------|-------------|-------------|
| #1694 | theredrad | feat: add force viewport screenshot | 2026-02-01 |
| #1746 | ChiragBellara | fix: avoid Common Crawl calls for sitemap-only URL seeding | 2026-02-01 |
| #1714 | YuriNachos | fix: replace tf-playwright-stealth with playwright-stealth | 2026-02-01 |
| #1721 | YuriNachos | fix: respect `<base>` tag for relative link resolution in html2text | 2026-02-01 |
| #1719 | YuriNachos | fix: include GoogleSearchCrawler script.js in package distribution | 2026-02-01 |
| #1717 | YuriNachos | fix: allow local embeddings by removing OpenAI fallback | 2026-02-01 |
| #1720 | YuriNachos | closed: LLM schema markdown fences (already fixed on develop) | 2026-02-01 |
| #1703 | — | closed: duplicate of #1721 | 2026-02-01 |
| #1698 | — | closed: duplicate of #1721 | 2026-02-01 |
| #1697 | — | closed: duplicate of #1717 | 2026-02-01 |
| #1710 | — | closed: duplicate of #1719 | 2026-02-01 |
