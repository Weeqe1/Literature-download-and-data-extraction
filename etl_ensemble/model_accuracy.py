# etl_ensemble/model_accuracy.py
"""Model accuracy evaluation and comparison module.

Provides:
- Per-model field coverage statistics
- Cross-model agreement/consistency matrix
- Accuracy calculation against human-reviewed ground truth
- Comprehensive extraction quality report

Usage:
    from etl_ensemble.model_accuracy import ModelAccuracyEvaluator
    
    evaluator = ModelAccuracyEvaluator(schema_fields)
    evaluator.add_extraction("model_a", extracted_dict)
    evaluator.add_extraction("model_b", extracted_dict)
    
    report = evaluator.generate_report()
    evaluator.save_report("accuracy_report.json")
"""

import json
import os
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict
from datetime import datetime

import logging
logger = logging.getLogger(__name__)


class ModelAccuracyEvaluator:
    """Evaluate and compare extraction accuracy across multiple models.
    
    Tracks field coverage, cross-model agreement, and optional ground truth accuracy.
    """
    
    def __init__(self, schema_fields: List[str], model_ids: Optional[List[str]] = None):
        """Initialize evaluator.
        
        Args:
            schema_fields: List of expected field names from schema.
            model_ids: Optional list of model IDs to track. If None, auto-detected.
        """
        self.schema_fields = schema_fields
        self.model_ids = model_ids or []
        
        # Per-model extraction data: model_id -> list of sample dicts
        self._extractions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # Ground truth data (if available): sample_id -> dict
        self._ground_truth: Dict[str, Dict[str, Any]] = {}
        
        # Track paper-level metadata for grouping
        self._paper_samples: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)  # paper_id -> [(model_id, sample)]
    
    def add_extraction(self, model_id: str, sample: Dict[str, Any], paper_id: Optional[str] = None) -> None:
        """Add an extraction result from a model.
        
        Args:
            model_id: Model identifier.
            sample: Extracted data dict.
            paper_id: Optional paper/sample identifier for grouping.
        """
        if model_id not in self.model_ids:
            self.model_ids.append(model_id)
        
        self._extractions[model_id].append(sample)
        
        if paper_id:
            self._paper_samples[paper_id].append((model_id, sample))
    
    def add_ground_truth(self, sample_id: str, truth: Dict[str, Any]) -> None:
        """Add ground truth data for accuracy evaluation.
        
        Args:
            sample_id: Sample identifier.
            truth: Ground truth data dict.
        """
        self._ground_truth[sample_id] = truth
    
    def load_extractions_from_dir(self, extraction_dir: str) -> int:
        """Load all extraction JSON files from a directory.
        
        Args:
            extraction_dir: Directory containing extraction JSON files.
            
        Returns:
            Number of files loaded.
        """
        count = 0
        if not os.path.isdir(extraction_dir):
            logger.warning("Extraction directory not found: %s", extraction_dir)
            return 0
        
        for fname in os.listdir(extraction_dir):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(extraction_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extract paper metadata for grouping
                paper_meta = data.get('paper_metadata', {})
                paper_id = paper_meta.get('doi') or paper_meta.get('title') or fname
                
                # Load samples with their model attribution
                samples = data.get('samples', [])
                models_used = data.get('meta', {}).get('models_used', [])
                
                for sample in samples:
                    # Determine which model extracted this sample
                    extracted_by = sample.get('_extracted_by', 'unknown')
                    if extracted_by == 'unknown' and models_used:
                        extracted_by = models_used[0]  # fallback to first model
                    
                    self.add_extraction(extracted_by, sample, paper_id)
                    count += 1
                    
            except Exception as e:
                logger.warning("Failed to load %s: %s", fname, e)
        
        logger.info("Loaded %d samples from %s", count, extraction_dir)
        return count
    
    def get_field_coverage(self, model_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Calculate field coverage statistics.
        
        Args:
            model_id: Specific model to analyze, or None for all models.
            
        Returns:
            Dict mapping field_name -> {total, filled, coverage_pct, sample_values}
        """
        result = {}
        
        models = [model_id] if model_id else self.model_ids
        
        for field in self.schema_fields:
            total = 0
            filled = 0
            sample_values = []
            
            for mid in models:
                for sample in self._extractions.get(mid, []):
                    total += 1
                    val = sample.get(field)
                    if val is not None and val != "" and val != "Not Specified":
                        filled += 1
                        if len(sample_values) < 5:  # Keep up to 5 sample values
                            sample_values.append(val)
            
            coverage_pct = (filled / total * 100) if total > 0 else 0
            result[field] = {
                "total_samples": total,
                "filled": filled,
                "empty": total - filled,
                "coverage_pct": round(coverage_pct, 1),
                "sample_values": sample_values,
            }
        
        return result
    
    def get_per_model_coverage(self) -> Dict[str, Dict[str, float]]:
        """Get field coverage percentage per model.
        
        Returns:
            Dict mapping model_id -> {field_name: coverage_pct}
        """
        result = {}
        
        for model_id in self.model_ids:
            coverage = self.get_field_coverage(model_id)
            result[model_id] = {
                field: stats["coverage_pct"]
                for field, stats in coverage.items()
            }
        
        return result
    
    def get_cross_model_agreement(self, numeric_tolerance: float = 0.05) -> Dict[str, Any]:
        """Calculate cross-model agreement matrix.
        
        Args:
            numeric_tolerance: Relative tolerance for numeric comparisons.
            
        Returns:
            Dict with pairwise agreement rates and field-level agreement.
        """
        if len(self.model_ids) < 2:
            return {"error": "Need at least 2 models for agreement calculation"}
        
        # Group samples by paper for comparison
        pairwise_agreement = defaultdict(lambda: {"agree": 0, "comparable": 0})
        field_agreement = defaultdict(lambda: {"agree": 0, "comparable": 0})
        
        for paper_id, model_samples in self._paper_samples.items():
            if len(model_samples) < 2:
                continue
            
            # Compare all pairs
            for i in range(len(model_samples)):
                for j in range(i + 1, len(model_samples)):
                    model_a, sample_a = model_samples[i]
                    model_b, sample_b = model_samples[j]
                    pair_key = f"{model_a}__vs__{model_b}"
                    
                    for field in self.schema_fields:
                        val_a = sample_a.get(field)
                        val_b = sample_b.get(field)
                        
                        # Skip if both are missing
                        if self._is_empty(val_a) and self._is_empty(val_b):
                            continue
                        
                        # Count as comparable
                        pairwise_agreement[pair_key]["comparable"] += 1
                        field_agreement[field]["comparable"] += 1
                        
                        # Check agreement
                        if self._values_agree(val_a, val_b, numeric_tolerance):
                            pairwise_agreement[pair_key]["agree"] += 1
                            field_agreement[field]["agree"] += 1
        
        # Calculate rates
        pairwise_rates = {}
        for pair, counts in pairwise_agreement.items():
            rate = counts["agree"] / counts["comparable"] if counts["comparable"] > 0 else 0
            pairwise_rates[pair] = {
                "agreement_rate": round(rate, 3),
                "agree": counts["agree"],
                "comparable": counts["comparable"],
            }
        
        field_rates = {}
        for field, counts in field_agreement.items():
            rate = counts["agree"] / counts["comparable"] if counts["comparable"] > 0 else 0
            field_rates[field] = {
                "agreement_rate": round(rate, 3),
                "agree": counts["agree"],
                "comparable": counts["comparable"],
            }
        
        return {
            "pairwise": pairwise_rates,
            "by_field": field_rates,
        }
    
    def get_accuracy_vs_ground_truth(self) -> Dict[str, Dict[str, Any]]:
        """Calculate accuracy against ground truth (if available).
        
        Returns:
            Dict mapping model_id -> {field -> accuracy_stats}
        """
        if not self._ground_truth:
            return {"error": "No ground truth data available"}
        
        result = {}
        
        for model_id in self.model_ids:
            model_stats = {}
            total_correct = 0
            total_comparable = 0
            
            for sample in self._extractions.get(model_id, []):
                sample_id = sample.get('sample_id') or sample.get('paper_doi') or sample.get('paper_title')
                if not sample_id or sample_id not in self._ground_truth:
                    continue
                
                truth = self._ground_truth[sample_id]
                
                for field in self.schema_fields:
                    pred_val = sample.get(field)
                    true_val = truth.get(field)
                    
                    if self._is_empty(true_val):
                        continue
                    
                    total_comparable += 1
                    
                    if field not in model_stats:
                        model_stats[field] = {"correct": 0, "total": 0, "examples": []}
                    
                    model_stats[field]["total"] += 1
                    
                    if self._values_agree(pred_val, true_val, 0.05):
                        model_stats[field]["correct"] += 1
                        total_correct += 1
                    else:
                        if len(model_stats[field]["examples"]) < 3:
                            model_stats[field]["examples"].append({
                                "predicted": str(pred_val)[:100],
                                "expected": str(true_val)[:100],
                            })
            
            # Calculate per-field accuracy
            for field, stats in model_stats.items():
                stats["accuracy"] = round(stats["correct"] / stats["total"], 3) if stats["total"] > 0 else 0
            
            result[model_id] = {
                "overall_accuracy": round(total_correct / total_comparable, 3) if total_comparable > 0 else 0,
                "total_correct": total_correct,
                "total_comparable": total_comparable,
                "per_field": model_stats,
            }
        
        return result
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive accuracy report.
        
        Returns:
            Dict with all evaluation metrics.
        """
        report = {
            "generated_at": datetime.now().isoformat(),
            "schema_fields": self.schema_fields,
            "models_evaluated": self.model_ids,
            "total_samples_per_model": {
                mid: len(samples) for mid, samples in self._extractions.items()
            },
            "field_coverage": self.get_field_coverage(),
            "per_model_coverage": self.get_per_model_coverage(),
            "cross_model_agreement": self.get_cross_model_agreement(),
        }
        
        # Add ground truth accuracy if available
        if self._ground_truth:
            report["accuracy_vs_ground_truth"] = self.get_accuracy_vs_ground_truth()
        
        # Add summary statistics
        report["summary"] = self._generate_summary(report)
        
        return report
    
    def save_report(self, output_path: str) -> None:
        """Save accuracy report to JSON file.
        
        Args:
            output_path: Path to output JSON file.
        """
        report = self.generate_report()
        
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info("Accuracy report saved to %s", output_path)
    
    def _generate_summary(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics from report data.
        
        Args:
            report: Full report dict.
            
        Returns:
            Summary dict.
        """
        summary = {}
        
        # Overall coverage summary
        coverage = report.get("field_coverage", {})
        if coverage:
            avg_coverage = sum(f["coverage_pct"] for f in coverage.values()) / len(coverage)
            best_fields = sorted(coverage.items(), key=lambda x: -x[1]["coverage_pct"])[:5]
            worst_fields = sorted(coverage.items(), key=lambda x: x[1]["coverage_pct"])[:5]
            
            summary["overall_coverage"] = {
                "average_pct": round(avg_coverage, 1),
                "best_fields": [{"field": f, "coverage": s["coverage_pct"]} for f, s in best_fields],
                "worst_fields": [{"field": f, "coverage": s["coverage_pct"]} for f, s in worst_fields],
            }
        
        # Per-model ranking
        per_model = report.get("per_model_coverage", {})
        if per_model:
            model_avg = {
                mid: sum(coverages.values()) / len(coverages) if coverages else 0
                for mid, coverages in per_model.items()
            }
            model_ranking = sorted(model_avg.items(), key=lambda x: -x[1])
            summary["model_ranking_by_coverage"] = [
                {"model": mid, "avg_coverage_pct": round(avg, 1)}
                for mid, avg in model_ranking
            ]
        
        # Agreement summary
        agreement = report.get("cross_model_agreement", {})
        pairwise = agreement.get("pairwise", {})
        if pairwise:
            avg_agreement = sum(p["agreement_rate"] for p in pairwise.values()) / len(pairwise)
            summary["average_cross_model_agreement"] = round(avg_agreement, 3)
        
        # Ground truth accuracy summary (if available)
        accuracy = report.get("accuracy_vs_ground_truth", {})
        if accuracy and "error" not in accuracy:
            model_accuracies = {
                mid: data.get("overall_accuracy", 0)
                for mid, data in accuracy.items()
                if isinstance(data, dict) and "overall_accuracy" in data
            }
            if model_accuracies:
                accuracy_ranking = sorted(model_accuracies.items(), key=lambda x: -x[1])
                summary["model_ranking_by_accuracy"] = [
                    {"model": mid, "accuracy": round(acc, 3)}
                    for mid, acc in accuracy_ranking
                ]
        
        return summary
    
    @staticmethod
    def _is_empty(val: Any) -> bool:
        """Check if a value is considered empty/missing."""
        if val is None:
            return True
        if isinstance(val, str) and val.strip() in ("", "Not Specified", "null", "None"):
            return True
        return False
    
    @staticmethod
    def _values_agree(val_a: Any, val_b: Any, tolerance: float = 0.05) -> bool:
        """Check if two values agree within tolerance.
        
        Args:
            val_a: First value.
            val_b: Second value.
            tolerance: Relative tolerance for numeric values.
            
        Returns:
            True if values agree.
        """
        # Both empty = agree
        if ModelAccuracyEvaluator._is_empty(val_a) and ModelAccuracyEvaluator._is_empty(val_b):
            return True
        
        # One empty, one not = disagree
        if ModelAccuracyEvaluator._is_empty(val_a) or ModelAccuracyEvaluator._is_empty(val_b):
            return False
        
        # Try numeric comparison
        try:
            num_a = float(val_a)
            num_b = float(val_b)
            if num_a == 0 and num_b == 0:
                return True
            max_val = max(abs(num_a), abs(num_b))
            return abs(num_a - num_b) / max_val <= tolerance
        except (ValueError, TypeError):
            pass
        
        # String comparison (normalized)
        def normalize(s: Any) -> str:
            return str(s).strip().lower().replace("-", "").replace("_", "")
        
        return normalize(val_a) == normalize(val_b)


def generate_extraction_report(
    extraction_dir: str,
    schema_fields: List[str],
    output_path: str,
    ground_truth_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience function to generate extraction report from directory.
    
    Args:
        extraction_dir: Directory containing extraction JSON files.
        schema_fields: List of expected field names.
        output_path: Path to save report JSON.
        ground_truth_path: Optional path to ground truth JSON file.
        
    Returns:
        Report dict.
    """
    evaluator = ModelAccuracyEvaluator(schema_fields)
    evaluator.load_extractions_from_dir(extraction_dir)
    
    if ground_truth_path and os.path.exists(ground_truth_path):
        try:
            with open(ground_truth_path, 'r', encoding='utf-8') as f:
                gt_data = json.load(f)
            # Support both dict and list formats
            if isinstance(gt_data, dict):
                for sample_id, truth in gt_data.items():
                    evaluator.add_ground_truth(sample_id, truth)
            elif isinstance(gt_data, list):
                for item in gt_data:
                    sid = item.get('sample_id') or item.get('doi') or item.get('title')
                    if sid:
                        evaluator.add_ground_truth(sid, item)
            logger.info("Loaded ground truth from %s", ground_truth_path)
        except Exception as e:
            logger.warning("Failed to load ground truth: %s", e)
    
    report = evaluator.generate_report()
    evaluator.save_report(output_path)
    
    return report
