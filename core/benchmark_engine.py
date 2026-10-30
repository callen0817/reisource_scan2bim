# -*- coding: utf-8 -*-
"""
reisource_scan2bim — Model Benchmarking & Reverse Engineering Engine
Compares Automated Scan2BIM Model against Manual Ground Truth BIM Model (Revit/IFC)
to calculate precision, recall, positional error, and extract learned architectural priors.
"""

import os
import json
import numpy as np

class BIMBenchmarkEngine:
    def __init__(self, gt_elements_path, auto_manifest_path):
        self.gt_elements_path = gt_elements_path
        self.auto_manifest_path = auto_manifest_path
        
        with open(gt_elements_path, "r", encoding="utf-8") as f:
            self.gt_all = json.load(f)
            
        with open(auto_manifest_path, "r", encoding="utf-8") as f:
            self.auto_manifest = json.load(f)
            
        # Filter GT elements to project space (X >= 2.5m)
        self.gt_project = [e for e in self.gt_all if e.get("center", [0])[0] >= 2.5]

    def benchmark_doors(self, tol=0.40):
        """Matches doors between GT and Automated BIM."""
        gt_doors = [e for e in self.gt_project if e.get("category") == "Doors"]
        auto_doors = self.auto_manifest.get("doors", [])
        
        matched_gt = set()
        matched_auto = set()
        pairs = []
        
        for ai, ad in enumerate(auto_doors):
            a_pos = np.array(ad.get("pos", [0, 0, 0])[:2])
            best_dist = float("inf")
            best_gi = None
            for gi, gd in enumerate(gt_doors):
                if gi in matched_gt:
                    continue
                g_pos = np.array(gd.get("center", [0, 0, 0])[:2])
                dist = np.linalg.norm(a_pos - g_pos)
                if dist < best_dist and dist <= tol:
                    best_dist = dist
                    best_gi = gi
            if best_gi is not None:
                matched_gt.add(best_gi)
                matched_auto.add(ai)
                pairs.append({
                    "auto_id": ad.get("id"),
                    "gt_pos": gt_doors[best_gi]["center"][:2],
                    "auto_pos": ad["pos"][:2],
                    "dist_mm": round(best_dist * 1000, 1)
                })
                
        recall = len(matched_gt) / len(gt_doors) if gt_doors else 1.0
        precision = len(matched_auto) / len(auto_doors) if auto_doors else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        mean_error = np.mean([p["dist_mm"] for p in pairs]) if pairs else 0.0
        
        return {
            "category": "Doors",
            "gt_count": len(gt_doors),
            "auto_count": len(auto_doors),
            "matched_count": len(pairs),
            "recall": round(recall, 3),
            "precision": round(precision, 3),
            "f1_score": round(f1, 3),
            "mean_error_mm": round(mean_error, 1),
            "pairs": pairs,
            "unmatched_gt": [gt_doors[i]["center"][:2] for i in range(len(gt_doors)) if i not in matched_gt],
            "unmatched_auto": [auto_doors[i]["id"] for i in range(len(auto_doors)) if i not in matched_auto]
        }

    def benchmark_plumbing(self, tol=0.50):
        """Matches plumbing fixtures between GT and Automated BIM."""
        gt_plumb = [e for e in self.gt_project if e.get("category") == "Plumbing Fixtures"]
        auto_plumb = self.auto_manifest.get("plumbing", [])
        
        matched_gt = set()
        matched_auto = set()
        pairs = []
        
        for ai, ap in enumerate(auto_plumb):
            a_pos = np.array(ap.get("pos", [0, 0, 0])[:2])
            best_dist = float("inf")
            best_gi = None
            for gi, gp in enumerate(gt_plumb):
                if gi in matched_gt:
                    continue
                g_pos = np.array(gp.get("center", [0, 0, 0])[:2])
                dist = np.linalg.norm(a_pos - g_pos)
                if dist < best_dist and dist <= tol:
                    best_dist = dist
                    best_gi = gi
            if best_gi is not None:
                matched_gt.add(best_gi)
                matched_auto.add(ai)
                pairs.append({
                    "auto_id": ap.get("id"),
                    "gt_pos": gt_plumb[best_gi]["center"][:2],
                    "auto_pos": ap["pos"][:2],
                    "dist_mm": round(best_dist * 1000, 1)
                })
                
        recall = len(matched_gt) / len(gt_plumb) if gt_plumb else 1.0
        precision = len(matched_auto) / len(auto_plumb) if auto_plumb else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        mean_error = np.mean([p["dist_mm"] for p in pairs]) if pairs else 0.0
        
        return {
            "category": "Plumbing Fixtures",
            "gt_count": len(gt_plumb),
            "auto_count": len(auto_plumb),
            "matched_count": len(pairs),
            "recall": round(recall, 3),
            "precision": round(precision, 3),
            "f1_score": round(f1, 3),
            "mean_error_mm": round(mean_error, 1),
            "pairs": pairs,
            "unmatched_gt": [gt_plumb[i]["center"][:2] for i in range(len(gt_plumb)) if i not in matched_gt],
            "unmatched_auto": [auto_plumb[i]["id"] for i in range(len(auto_plumb)) if i not in matched_auto]
        }

    def benchmark_demising_walls(self):
        """Compares primary demising walls (North, South, East, West)."""
        gt_walls = [e for e in self.gt_project if e.get("category") == "Walls"]
        auto_walls = {w["id"]: w for w in self.auto_manifest.get("walls", [])}
        
        # Demising GT targets:
        # North: Y ~ 0.983, Length > 10m
        gt_north = [w for w in gt_walls if abs(w["center"][1] - 0.983) < 0.1 and w["size"][0] > 10][0]
        # South: Y ~ -4.287, Length > 10m
        gt_south = [w for w in gt_walls if abs(w["center"][1] - (-4.287)) < 0.1 and w["size"][0] > 10][0]
        # East: X ~ 18.538
        gt_east = [w for w in gt_walls if abs(w["center"][0] - 18.538) < 0.1 and w["size"][1] > 3][0]
        
        auto_north = auto_walls.get("W_EXT_NORTH")
        auto_south = auto_walls.get("W_EXT_SOUTH_A")
        auto_east = auto_walls.get("W_EXT_EAST_A")
        
        diffs = {}
        if auto_north:
            mid_y = (auto_north["p1"][1] + auto_north["p2"][1]) / 2.0
            diffs["North_Demising"] = {
                "gt_y": gt_north["center"][1],
                "auto_mid_y": round(mid_y, 3),
                "delta_y_mm": round(abs(mid_y - gt_north["center"][1]) * 1000, 1),
                "gt_height": gt_north["size"][2],
                "auto_height": auto_north["height"],
                "delta_h_mm": round(abs(auto_north["height"] - gt_north["size"][2]) * 1000, 1)
            }
        if auto_south:
            diffs["South_Demising"] = {
                "gt_y": gt_south["center"][1],
                "auto_y": auto_south["p1"][1],
                "delta_y_mm": round(abs(auto_south["p1"][1] - gt_south["center"][1]) * 1000, 1),
                "gt_height": gt_south["size"][2],
                "auto_height": auto_south["height"],
                "delta_h_mm": round(abs(auto_south["height"] - gt_south["size"][2]) * 1000, 1)
            }
        if auto_east:
            diffs["East_Demising"] = {
                "gt_x": gt_east["center"][0],
                "auto_x": auto_east["p1"][0],
                "delta_x_mm": round(abs(auto_east["p1"][0] - gt_east["center"][0]) * 1000, 1),
                "gt_height": gt_east["size"][2],
                "auto_height": auto_east["height"],
                "delta_h_mm": round(abs(auto_east["height"] - gt_east["size"][2]) * 1000, 1)
            }
        return diffs

    def run_full_benchmark(self):
        doors_res = self.benchmark_doors()
        plumb_res = self.benchmark_plumbing()
        demising_res = self.benchmark_demising_walls()
        
        report = {
            "doors_evaluation": doors_res,
            "plumbing_evaluation": plumb_res,
            "demising_evaluation": demising_res,
            "overall_summary": {
                "doors_f1": doors_res["f1_score"],
                "plumbing_f1": plumb_res["f1_score"],
                "doors_mean_error_mm": doors_res["mean_error_mm"],
                "plumbing_mean_error_mm": plumb_res["mean_error_mm"]
            }
        }
        return report

if __name__ == "__main__":
    gt_path = r"C:\Users\calle\.gemini\antigravity\scratch\eyesonpark_gt\all_placed_building_elements.json"
    auto_manifest = r"C:\Users\calle\.gemini\antigravity\scratch\reisource_scan2bim\data\eyesonpark_bim_manifest.json"
    
    engine = BIMBenchmarkEngine(gt_path, auto_manifest)
    res = engine.run_full_benchmark()
    print(json.dumps(res, indent=2))
