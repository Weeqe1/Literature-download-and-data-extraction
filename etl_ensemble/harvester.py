"""Literature harvester: orchestration, merge, dedupe, and main entry point.

Provides the ``LiteratureHarvester`` class and a legacy ``main()`` function
that reads config, splits keywords into clauses, searches all sources,
merges results, fills missing DOIs, and kicks off downloading.
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple

import requests
import pandas as pd
from tqdm import tqdm

import logging
logger = logging.getLogger(__name__)

from .sources.base import (
    sanitize_filename,
    doi_normalize,
    safe_get,
    normalize_text,
    parse_clause_units,
    match_work_against_clause_with_reason,
    split_keywords_into_clauses,
    build_source_query,
    set_source_stats,
    get_source_stats,
    configure_rate_limit,
    rate_limit,
)
from .sources import openalex, wos, semantic_scholar, pubmed as pubmed_mod, arxiv as arxiv_mod, crossref
from .downloader import download_pdfs_and_assemble, ensure_dir
from .pdf_checker import pdf_check_and_cleanup, check_pdf_valid, export_rejected_audit

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------
try:
    import yaml
except Exception:
    yaml = None

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None


# ---------------------------------------------------------------------------
# LiteratureHarvester class
# ---------------------------------------------------------------------------
class LiteratureHarvester:
    """Encapsulates the full literature harvest pipeline.

    Attributes:
        config: Parsed configuration dict.
        session: Shared ``requests.Session``.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialise harvester with optional config dict.

        Args:
            config: Configuration dict. If None, loads from YAML file.
        """
        self.config = config or {}
        self.session = requests.Session()
        self._email = self.get_config("api_keys.contact_email", "wangqi@ahut.edu.cn")
        self.session.headers.update({"User-Agent": "harvest_literature/1.0 (mailto:%s)" % self._email})

        # Propagate rate limit
        rps = self.get_config("runtime.requests_per_second", 4)
        configure_rate_limit(rps)

        # Configure source modules
        self._configure_sources()

    # ---- config helpers ----
    def get_config(self, key_path: str, default=None):
        """Get a config value by dot-separated path."""
        keys = key_path.split(".")
        val = self.config
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val if val is not None else default

    def _configure_sources(self) -> None:
        """Push configuration into source sub-modules."""
        openalex.configure(
            api_key=os.environ.get("OPENALEX_API_KEY", self.get_config("api_keys.openalex", "")),
            timeout_sec=int(self.get_config("runtime.openalex_timeout_sec", 45) or 45),
            retry_attempts=int(self.get_config("runtime.openalex_retry_attempts", 4) or 4),
            disable_on_budget_exhausted=bool(self.get_config("runtime.openalex_disable_on_budget_exhausted", True)),
            session=self.session,
        )
        wos.configure(api_key=os.environ.get("WOS_API_KEY", self.get_config("api_keys.wos", "")))
        semantic_scholar.configure(api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY", self.get_config("api_keys.semantic_scholar", "")))
        pubmed_mod.configure(email=self._email)

    # ---- work_to_row ----
    @staticmethod
    def _extract_journal_from_work(work: dict) -> Optional[str]:
        if not work:
            return None
        if work.get("journal"):
            return work.get("journal")
        if work.get("primary_location"):
            return safe_get(work, "primary_location", "source", "display_name")
        if work.get("locations"):
            for loc in work.get("locations") or []:
                s = loc.get("source") or {}
                if s.get("display_name"):
                    return s.get("display_name")
        return None

    @staticmethod
    def work_to_row(work: dict) -> Dict[str, Any]:
        """Convert a raw work dict to a normalised row for DataFrame."""
        row = {}
        row["title"] = work.get("display_name") or work.get("title") or ""
        row["abstract"] = work.get("abstract_text") or work.get("abstract") or ""
        row["journal"] = work.get("journal") or LiteratureHarvester._extract_journal_from_work(work) or ""
        row["year"] = work.get("publication_year") or work.get("year") or ""
        row["doi"] = doi_normalize(work.get("doi") or "")
        alist = work.get("authors_list") or []
        if not alist and work.get("authorships"):
            alist = [a.get("author", {}).get("display_name") for a in work.get("authorships") or [] if a.get("author")]
        row["authors"] = "; ".join([a for a in alist if a])
        row["affiliations"] = work.get("affiliations") or ""
        row["cited_by_count"] = work.get("cited_by_count") or work.get("timesCited") or None
        row["open_access_status"] = work.get("open_access") or work.get("open_access_status") or work.get("is_oa") or None
        row["pdf_url"] = (
            work.get("oa_url")
            or safe_get(work, "openAccessPdf", "url")
            or safe_get(work, "best_oa_location", "url_for_pdf")
            or safe_get(work, "best_oa_location", "url")
        )
        row["source"] = work.get("source") or ""
        return row

    # ---- source dispatch ----
    def _call_source(self, src: str, q: str, title_only_flag: bool) -> List[dict]:
        """Call the appropriate source search function."""
        mailto = self._email
        year_from = self.get_config("search.year_from", 2000)
        year_to = self.get_config("search.year_to", 2030)
        max_per_clause = self.get_config("search.max_results_per_clause", 200)
        semantic_api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", self.get_config("api_keys.semantic_scholar", ""))

        try:
            if src == "openalex":
                return openalex.search_openalex_clause(q, max_results=max_per_clause, title_only=title_only_flag, year_from=year_from, year_to=year_to, mailto=mailto)
            if src == "wos":
                return wos.search_wos_clause(q, max_results=max_per_clause, year_from=year_from, year_to=year_to)
            if src == "semantic_scholar":
                return semantic_scholar.search_semantic_scholar_clause(q, max_results=max_per_clause, title_only=title_only_flag, api_key=semantic_api_key, year_from=year_from, year_to=year_to)
            if src == "pubmed":
                return pubmed_mod.search_pubmed_clause(q, max_results=max_per_clause, title_only=title_only_flag, email=mailto)
            if src == "arxiv":
                return arxiv_mod.search_arxiv_clause(q, max_results=max_per_clause, title_only=title_only_flag)
            if src == "crossref":
                return crossref.search_crossref_clause(q, max_results=max_per_clause, mailto=mailto, year_from=year_from, year_to=year_to, title_only=title_only_flag)
        except Exception as e:
            logger.warning("[%s] exception: %s", src, e)
        return []

    # ---- run_clause_search ----
    def run_clause_search(
        self,
        clause: str,
        sources_order: List[str],
        max_per_clause: int = 200,
        verbose: bool = True,
        audit_rejections: Optional[List[Dict[str, Any]]] = None,
        audit_limit: int = 2000,
        match_strictness: float = 0.7,
    ) -> List[dict]:
        """Run configured sources for a single clause (title-only + title+abstract rounds).

        Args:
            clause: Boolean search clause.
            sources_order: List of source names in priority order.
            max_per_clause: Max results per source per round.
            verbose: Log progress.
            audit_rejections: Collect rejected items for audit export.
            audit_limit: Max audit items to collect.
            match_strictness: 0.0-1.0 fraction of terms required to match.

        Returns:
            List of matched work dicts.
        """
        collected: List[dict] = []
        try:
            match_strictness = float(match_strictness)
        except Exception:
            match_strictness = 0.7
        match_strictness = max(0.0, min(1.0, match_strictness))

        def is_valid_clause(c: str) -> bool:
            if not c or not c.strip():
                return False
            s = c.strip()
            if len(re.sub(r'[^A-Za-z0-9]', '', s)) < 3:
                return False
            if re.fullmatch(r'^(AND|OR|NOT|\s)+$', s, flags=re.I):
                return False
            return True

        if not is_valid_clause(clause):
            if verbose:
                logger.info("[RunClause] skipping invalid clause: %s", clause)
            return []

        for title_only in (True, False):
            which = "title-only" if title_only else "title+abstract"
            for src in sources_order:
                q = build_source_query(src, clause, title_only=title_only)

                if verbose:
                    logger.info("[%s] querying (%s): %s", src, which, q if len(q) < 200 else q[:200] + '...')
                items = self._call_source(src, q, title_only)
                if items:
                    filtered = []
                    for it in items:
                        ok, reason = match_work_against_clause_with_reason(
                            it, clause, title_only=title_only, match_strictness=match_strictness
                        )
                        if ok:
                            filtered.append(it)
                        else:
                            if audit_rejections is not None and len(audit_rejections) < max(0, audit_limit):
                                audit_rejections.append({
                                    "clause": clause,
                                    "source": src,
                                    "round": which,
                                    "reason": reason,
                                    "title": it.get("display_name") or it.get("title") or "",
                                    "doi": doi_normalize(it.get("doi") or ""),
                                    "year": it.get("publication_year") or it.get("year") or None,
                                    "journal": it.get("journal") or self._extract_journal_from_work(it) or "",
                                })
                    if verbose:
                        logger.info("[%s] returned %d items, kept %d after clause match", src, len(items), len(filtered))
                        stats = get_source_stats(src)
                        logger.info("[%s] dbg %d -> %d -> %d", src, stats.get("scanned_raw", len(items)), stats.get("returned", len(items)), len(filtered))
                    collected.extend(filtered)
                else:
                    if verbose:
                        logger.info("[%s] returned 0 items for clause", src)
                        stats = get_source_stats(src)
                        logger.info("[%s] dbg %d -> %d -> 0", src, stats.get("scanned_raw", 0), stats.get("returned", 0))
        return collected

    # ---- merge / dedupe ----
    @staticmethod
    def merge_and_dedupe(works_all: List[dict], max_total: int = 10000) -> List[dict]:
        """Merge and deduplicate works by DOI or title.

        Args:
            works_all: Raw list of work dicts from all sources/clauses.
            max_total: Maximum total works to keep.

        Returns:
            Deduplicated list.
        """
        seen: Dict[str, dict] = {}
        merged: List[dict] = []
        for w in works_all:
            doi = doi_normalize(w.get("doi") or "")
            title = (w.get("display_name") or w.get("title") or "").strip().lower()
            key = doi if doi else ("title:" + title)
            if not key:
                continue
            if key in seen:
                old = seen[key]
                for fld in ("abstract_text", "journal", "publication_year", "authors_list", "open_access_status", "pdf_url", "cited_by_count"):
                    if not old.get(fld) and w.get(fld):
                        old[fld] = w.get(fld)
                continue
            seen[key] = w
            merged.append(w)
            if len(merged) >= max_total:
                break
        return merged

    # ---- fill missing DOIs ----
    def fill_missing_dois(self, rows: List[Dict[str, Any]], verbose: bool = True) -> List[Dict[str, Any]]:
        """Use Crossref title lookup to fill in missing DOIs.

        Args:
            rows: List of work/row dicts.
            verbose: Log progress.

        Returns:
            Same list (modified in-place) with DOIs filled where possible.
        """
        missing = [r for r in rows if not r.get("doi")]
        if not missing:
            if verbose:
                logger.info("[Fill] no missing DOIs")
            return rows
        if verbose:
            logger.info("[Fill] trying to find missing DOIs for %d items via Crossref", len(missing))
        for r in tqdm(missing, desc="Finding DOIs"):
            title = r.get("display_name") or r.get("title") or ""
            if not title:
                continue
            found = crossref.crossref_find_doi_by_title(title, mailto=self._email)
            if found:
                r["doi"] = found
        return rows

    # ---- main pipeline ----
    def run(self) -> None:
        """Execute the full literature harvest pipeline."""
        keywords_raw = self.get_config("search.keywords", "")
        if keywords_raw:
            keywords = " ".join(keywords_raw.strip().split("\n"))
        else:
            keywords = '("nano fluorescent probe") OR ("nanoscale fluorescent probe") OR ("fluorescent nanoprobe")'

        out_base = self.get_config("output.base_dir", "outputs/literature")
        excel_filename = self.get_config("output.excel_filename", "nano_fluorescent_probes.xlsx")
        excel_path = os.path.join(out_base, excel_filename)
        audit_filename = self.get_config("output.audit_rejected_filename", "filtered_out_audit.xlsx")
        audit_limit = self.get_config("output.audit_rejected_limit", 2000)
        audit_path = os.path.join(out_base, audit_filename)

        sources_order = self.get_config("search.sources_order", ["openalex", "wos", "semantic_scholar", "pubmed", "arxiv", "crossref"])
        max_results_per_clause = self.get_config("search.max_results_per_clause", 200)
        max_total = self.get_config("search.max_total", 10000)
        max_clauses = self.get_config("search.max_clauses", 50)
        year_from = self.get_config("search.year_from", 2000)
        year_to = self.get_config("search.year_to", 2030)
        incremental = self.get_config("runtime.incremental", True)
        verbose = self.get_config("runtime.verbose", True)
        match_strictness = self.get_config("runtime.match_strictness", 0.7)

        ensure_dir(out_base)

        existing_dois: set = set()
        if incremental and os.path.exists(excel_path):
            try:
                df_exist = pd.read_excel(excel_path)
                doi_values = df_exist["doi"].tolist() if "doi" in df_exist.columns else []
                for d in doi_values:
                    if pd.isna(d):
                        continue
                    ds = str(d).strip()
                    if ds:
                        existing_dois.add(ds)
                logger.info("[Incremental] Loaded %d existing DOIs from %s", len(existing_dois), excel_path)
            except Exception as e:
                logger.warning("[Incremental] could not read existing excel: %s", e)

        clauses = split_keywords_into_clauses(keywords, max_clauses=max_clauses)
        logger.info("[Split] derived %d clauses from keywords.", len(clauses))
        for i, c in enumerate(clauses, start=1):
            logger.info("[Clause %d] %s", i, c)

        all_works: List[dict] = []
        rejected_audit: List[Dict[str, Any]] = []
        for idx, clause in enumerate(clauses, start=1):
            logger.info("[RunClause] (%d/%d) starting clause: %s", idx, len(clauses), clause)
            works = self.run_clause_search(
                clause,
                sources_order=sources_order,
                max_per_clause=max_results_per_clause,
                verbose=True,
                audit_rejections=rejected_audit,
                audit_limit=audit_limit,
                match_strictness=match_strictness,
            )
            logger.info("[RunClause] clause %d returned %d raw works", idx, len(works))
            all_works.extend(works)
            if len(all_works) >= max_total:
                logger.info("[Main] reached max_total cap, stopping clause loop")
                break

        export_rejected_audit(rejected_audit, audit_path, verbose=True)

        logger.info("[Merge] merging and deduplicating...")
        merged = self.merge_and_dedupe(all_works, max_total=max_total)
        logger.info("[Merge] merged total: %d (capped to %d)", len(merged), max_total)

        logger.info("[Fill] filling missing DOIs via Crossref title lookup...")
        merged = self.fill_missing_dois(merged, verbose=True)

        # Quality control
        logger.info("[Quality] validating and cleaning metadata...")
        try:
            from quality_control import LiteratureQualityController
            qc = LiteratureQualityController()
            merged = qc.validate_and_clean_metadata(merged)
            logger.info("[Quality] cleaned %d works", len(merged))

            quality_enabled = self.get_config("quality.enabled", False)
            if quality_enabled:
                logger.info("[Quality] filtering literature by relevance and completeness...")
                min_relevance = self.get_config("quality.min_relevance", 0.05)
                min_completeness = self.get_config("quality.min_completeness", 0.1)
                min_overall = self.get_config("quality.min_overall", 0.1)
                filtered_works, stats = qc.filter_literature(
                    merged, min_relevance=min_relevance, min_completeness=min_completeness, min_overall=min_overall
                )
                logger.info("[Quality] Filter: input=%d, passed=%d", stats['total_input'], stats['passed_filter'])
                merged = filtered_works
            else:
                logger.info("[Quality] quality filtering disabled (set quality.enabled=true to enable)")
        except ImportError:
            logger.warning("[Warning] quality_control module not found, skipping quality filtering")

        if incremental and existing_dois:
            kept = []
            skipped = 0
            for w in merged:
                d = doi_normalize(w.get("doi") or "")
                if d and d in existing_dois:
                    skipped += 1
                    continue
                kept.append(w)
            logger.info("[Incremental] Skipped %d existing DOIs; %d new works remain.", skipped, len(kept))
            merged = kept

        logger.info("[Download] attempting to download OA PDFs and assembling table...")
        max_workers = self.get_config("runtime.max_concurrent_downloads", 4)
        checkpoint_interval = self.get_config("runtime.checkpoint_interval", 100)
        checkpoint_path = os.path.join(out_base, "_checkpoint.xlsx")

        df_final = download_pdfs_and_assemble(
            merged, out_base, mailto=self._email, email=self._email,
            max_workers=max_workers, checkpoint_interval=checkpoint_interval,
            checkpoint_path=checkpoint_path, verbose=verbose,
        )

        if incremental and os.path.exists(excel_path):
            try:
                old = pd.read_excel(excel_path)
                combined = pd.concat([old, df_final], ignore_index=True)
                combined["doi_norm"] = combined["doi"].apply(lambda x: doi_normalize(str(x)) if pd.notna(x) else None)
                combined = combined.sort_values(["year", "journal", "title"], ascending=[False, True, True])
                combined = combined.drop_duplicates(subset=["doi_norm", "title"], keep="first")
                combined = combined.drop(columns=["doi_norm"], errors="ignore")
                final_df = combined
            except Exception:
                final_df = df_final
        else:
            final_df = df_final

        ensure_dir(out_base)
        final_df.to_excel(excel_path, index=False)
        logger.info("[OK] XLSX written: %s (%d rows)", excel_path, len(final_df))

        logger.info("[PDF-Check] verifying downloaded PDFs...")
        pdf_check_log_each = self.get_config("runtime.pdf_check_log_each", False)
        pdf_check_remove_invalid_rows = self.get_config("runtime.pdf_check_remove_invalid_rows", False)
        checked, removed = pdf_check_and_cleanup(
            excel_path, os.path.join(out_base, "PDF_download"),
            backup=True, verbose=verbose,
            log_each=pdf_check_log_each,
            remove_invalid_rows=pdf_check_remove_invalid_rows,
        )

        n_oa = int(final_df["is_oa"].fillna(False).sum()) if "is_oa" in final_df.columns else 0
        logger.info("[Summary] total exported: %d; OA: %d; PDFs attempted: %d", len(final_df), n_oa, final_df['pdf_path'].notna().sum() if 'pdf_path' in final_df.columns else 0)
        logger.info("[Done]")


# ---------------------------------------------------------------------------
# Config loading helper (for thin entry point)
# ---------------------------------------------------------------------------
def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to harvest_config.yml. If None, uses default location.

    Returns:
        Parsed config dict.
    """
    if yaml is None:
        logger.warning("[Config] PyYAML not installed. Using default config values.")
        return {}
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "..", "configs", "harvest", "harvest_config.yml")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            logger.info("[Config] Loaded configuration from %s", config_path)
            return cfg
        except Exception as e:
            logger.warning("[Config] Failed to load config: %s. Using defaults.", e)
            return {}
    else:
        logger.warning("[Config] Config file not found: %s. Using defaults.", config_path)
        return {}


# ---------------------------------------------------------------------------
# Legacy main() entry point
# ---------------------------------------------------------------------------
def main():
    """Legacy entry point: loads config and runs LiteratureHarvester."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    cfg = load_config()
    harvester = LiteratureHarvester(config=cfg)
    harvester.run()


if __name__ == "__main__":
    main()
