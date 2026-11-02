#!/usr/bin/env python3
"""Classify cell lineages and subsets from markers and gate names."""

import re
from typing import List, Dict, Set, Optional, Tuple

class CellTypeClassifier:
    """Classify cell lineages and subsets using marker and gate-name rules."""

    def __init__(self):
        # T-cell lineage markers.
        self.t_cell_markers = {
            'CD3', 'CD3+', 'CD3pos', 'CD3_pos', 'CD3positive',
            'CD4', 'CD4+', 'CD4pos', 'CD4_pos', 'CD4positive',
            'CD8', 'CD8+', 'CD8pos', 'CD8_pos', 'CD8positive',
            'TCR', 'TCRab', 'TCRgd',
        }

        # B-cell lineage markers.
        self.b_cell_markers = {
            'CD19', 'CD19+', 'CD19pos', 'CD19_pos', 'CD19positive',
            'CD20', 'CD20+', 'CD20pos', 'CD20_pos', 'CD20positive',
            'CD22', 'CD22+', 'CD22pos', 'CD22_pos', 'CD22positive',
            'B220', 'B220+',
            'IgM', 'IgD', 'IgG',
        }

        # NK-cell lineage markers.
        self.nk_cell_markers = {
            'CD56', 'CD56+', 'CD56pos', 'CD56_pos',
            'NKp46', 'NKG2D', 'NKG2A',
            'NK1.1', 'NK',
        }

        # Myeloid and monocyte lineage markers.
        self.myeloid_markers = {
            'CD11b', 'CD11b+', 'CD11bpos',
            'CD11c', 'CD11c+', 'CD11cpos',
            'CD14', 'CD14+', 'CD14pos',
            'CD33', 'CD33+',
            'Ly6C', 'Ly6G',
            'F4/80',
        }

        # Dendritic-cell markers.
        self.dc_markers = {
            'CD11c', 'CD11c+',
            'CD86', 'CD86+',
            'CD80', 'CD80+',
            'MHCII', 'MHC-II', 'MHCII+',
        }

        # Activation and function markers are not lineage-specific.
        self.activation_markers = {
            'CD25', 'CD25+', 'CD25pos',  # IL-2 receptor marker associated with Tregs.
            'CD69', 'CD69+',  # Early activation marker.
            'CD38', 'CD38+', 'CD38pos',  # Activation marker; not lineage-specific.
            'HLA-DR', 'HLADR+',  # Activation marker.
            'Ki67', 'Ki67+', 'Ki-67',  # Proliferation marker.
        }

        # T-cell subset markers.
        self.t_cell_subset_markers = {
            'CD25': 'Regulatory',  # Supports Treg classification with CD4.
            'Foxp3': 'Regulatory',  # Regulatory T-cell marker.
            'CXCR5': 'Follicular Helper',  # Tfh-associated marker.
            'PD1': 'Follicular Helper',  # Tfh-associated marker.
            'CD127': 'Memory',  # CD127 expression supports effector/memory classification.
            'CD45RA': 'Naive',  # CD45RA expression supports naive-cell classification.
            'CD45RO': 'Memory',  # CD45RO expression supports memory-cell classification.
            'CCR7': 'Central Memory',  # CCR7 expression supports central-memory classification.
        }

        # B-cell subset markers.
        self.b_cell_subset_markers = {
            'IgD': 'Naive',  # IgD expression supports naive B-cell classification.
            'CD27': 'Memory',  # CD27 expression supports memory B-cell classification.
            'CD38': 'Germinal Center or Plasmablast',  # High CD38 expression occurs in germinal-center B cells and plasmablasts.
            'CD138': 'Plasma Cell',  # CD138 expression supports plasma-cell classification.
            'GL7': 'Germinal Center',  # GL7 expression supports germinal-center classification.
            'Fas': 'Germinal Center',  # Fas expression supports germinal-center classification.
        }

        # Negative markers used to exclude lineages.
        self.negative_exclusions = {
            'CD3-': ['T cell'],
            'CD3neg': ['T cell'],
            'CD19-': ['B cell'],
            'CD19neg': ['B cell'],
            'CD20-': ['B cell'],
            'CD4-': ['CD4+ T cell'],
            'CD8-': ['CD8+ T cell'],
        }

        # Common gate-name aliases.
        self.gate_patterns = {
            'Tconv': 'Conventional T Cell',
            'Treg': 'Regulatory T Cell',
            'Tfh': 'T Follicular Helper',
            'TFH': 'T Follicular Helper',
            'NK': 'NK Cell',
            'GC': 'Germinal Center B Cell',
            'Memory': 'Memory Cell',
            'Naive': 'Naive Cell',
            'Naïve': 'Naive Cell',
            'Plasma': 'Plasma Cell',
            'Plasmablast': 'Plasmablast',
            'central_memory': 'Central Memory',
            'effector_memory': 'Effector Memory',
            'CD4_central_memory': 'CD4+ Central Memory T Cell',
            'CD4_effector_memory': 'CD4+ Effector Memory T Cell',
            'CD8_central_memory': 'CD8+ Central Memory T Cell',
            'CD8_effector_memory': 'CD8+ Effector Memory T Cell',
            'CD4_naive': 'CD4+ Naive T Cell',
            'CD8_naive': 'CD8+ Naive T Cell',
            'CD4_prolif': 'CD4+ Proliferating T Cell',
            'CD8_prolif': 'CD8+ Proliferating T Cell',
            'CD19_pos': 'Total B Cell',
            'CD8_TEM': 'CD8+ TEM',
            'CD4_TEM': 'CD4+ TEM',
            'Total_CD8_T_Cells': 'Total CD8+ T Cells'
        }

    def extract_markers_from_path(self, gate_path: str) -> List[Tuple[str, str]]:
        """Parse marker/status pairs from a slash-delimited gate path.

        Marker names are uppercase; status is ``+``, ``-``, or an empty string.
        """
        markers = []
        parts = gate_path.split('/')

        for part in parts:

            for match in re.finditer(r'(CD\d+|[A-Z][a-z]*\d*[A-Z]*)([\+\-])', part, re.IGNORECASE):
                marker = match.group(1).upper()
                status = match.group(2)
                markers.append((marker, status))

            for match in re.finditer(r'(CD\d+|[A-Z][a-z]*\d*)(?:_|\b)(pos|neg|positive|negative)\b', part, re.IGNORECASE):
                marker = match.group(1).upper()
                status_text = match.group(2).lower()
                status = '+' if 'pos' in status_text else '-'
                markers.append((marker, status))

            for match in re.finditer(r'(CD\d+|[A-Z][a-z]*\d*)(pos|neg|positive|negative)\b', part, re.IGNORECASE):
                marker = match.group(1).upper()
                status_text = match.group(2).lower()
                status = '+' if 'pos' in status_text else '-'
                markers.append((marker, status))

            if not markers:
                for marker_set in [self.t_cell_markers, self.b_cell_markers, 
                                  self.nk_cell_markers, self.myeloid_markers]:
                    for marker in marker_set:
                        marker_clean = marker.replace('+', '').replace('pos', '').replace('_', '').replace('positive', '').replace('neg', '').replace('negative', '')
                        if marker_clean.upper() in part.upper() and len(marker_clean) > 2:
                            markers.append((marker_clean.upper(), '+'))
                            break

        return markers

    def classify_cell_lineage(self, gate_path: str) -> Dict[str, any]:
        """Score lineage candidates using marker evidence from the gate path."""
        markers = self.extract_markers_from_path(gate_path)

        scores = {
            'T cell': 0,
            'B cell': 0,
            'NK cell': 0,
            'Myeloid': 0,
            'Unknown': 0
        }

        evidence = []

        for marker, status in markers:
            marker_clean = marker.upper()

            if any(act in marker_clean for act in ['CD38', 'CD69', 'CD25', 'KI67', 'HLADR']):
                continue

            if status == '+':
                if any(t in marker_clean for t in ['CD3', 'CD4', 'CD8', 'TCR']):
                    scores['T cell'] += 3
                    evidence.append(f"{marker}+ indicates T cell")
            elif status == '-':
                if any(t in marker_clean for t in ['CD3', 'CD4', 'CD8']):
                    scores['T cell'] -= 2
                    evidence.append(f"{marker}- excludes T cell")

            if status == '+':
                if any(b in marker_clean for b in ['CD19', 'CD20', 'CD22', 'B220']):
                    scores['B cell'] += 3
                    evidence.append(f"{marker}+ indicates B cell")
            elif status == '-':
                if any(b in marker_clean for b in ['CD19', 'CD20']):
                    scores['B cell'] -= 2
                    evidence.append(f"{marker}- excludes B cell")

            if status == '+':
                if any(nk in marker_clean for nk in ['CD56', 'NK']):
                    scores['NK cell'] += 3
                    evidence.append(f"{marker}+ indicates NK cell")
                # CD3 negativity supports NK-cell classification.
                if 'CD3' in marker_clean and status == '-':
                    scores['NK cell'] += 1

            if status == '+':
                if any(m in marker_clean for m in ['CD11B', 'CD11C', 'CD14', 'CD33']):
                    scores['Myeloid'] += 2
                    evidence.append(f"{marker}+ indicates myeloid")

        gate_lower = gate_path.lower()
        if any(word in gate_lower for word in ['tconv', 'treg', 'tfh', 'tcell', 't_cell']):
            scores['T cell'] += 2
            evidence.append("Gate name suggests T cell")
        if any(word in gate_lower for word in ['bcell', 'b_cell', 'b-cell']):
            scores['B cell'] += 2
            evidence.append("Gate name suggests B cell")
        if 'nk' in gate_lower or 'natural_killer' in gate_lower:
            scores['NK cell'] += 2
            evidence.append("Gate name suggests NK cell")

        max_score = max(scores.values())
        if max_score <= 0:
            return {
                'lineage': 'Unknown',
                'confidence': 'Low',
                'score': 0,
                'evidence': ['No definitive markers found']
            }

        lineage = max(scores.keys(), key=lambda k: scores[k])
        confidence = 'High' if max_score >= 3 else 'Medium' if max_score >= 2 else 'Low'

        return {
            'lineage': lineage,
            'confidence': confidence,
            'score': scores[lineage],
            'evidence': evidence
        }

    def classify_cell_subset(self, gate_path: str, lineage: str) -> Optional[str]:
        """Classify a cell subset within the specified lineage."""
        gate_lower = gate_path.lower()

        for pattern, subset in self.gate_patterns.items():
            if pattern.lower() == gate_path.split('/')[-1].lower():
                return subset

        for pattern, subset in self.gate_patterns.items():
            if pattern.lower() in gate_lower:
                return subset

        markers = self.extract_markers_from_path(gate_path)

        if lineage == 'T cell':

            for marker, status in markers:
                if status == '+':
                    marker_upper = marker.upper()

                    if 'CD4' in marker_upper:

                        if any(m[0].upper() in ['CD25', 'FOXP3'] and m[1] == '+' for m in markers):
                            return 'Regulatory T Cell (Treg)'

                        if any(m[0].upper() in ['CXCR5', 'PD1', 'ICOS'] and m[1] == '+' for m in markers):
                            return 'Follicular Helper T Cell (Tfh)'
                        return 'CD4+ T Cell'

                    elif 'CD8' in marker_upper:
                        return 'CD8+ T Cell'

                    if 'CD45RO' in marker_upper:
                        return 'Memory T Cell'
                    if 'CD45RA' in marker_upper:
                        return 'Naive T Cell'

        elif lineage == 'B cell':

            for marker, status in markers:
                if status == '+':
                    marker_upper = marker.upper()

                    if 'CD138' in marker_upper:
                        return 'Plasma Cell'
                    if 'CD38' in marker_upper and 'CD27' in [m[0].upper() for m in markers]:
                        return 'Plasmablast'
                    if any(gc in marker_upper for gc in ['GL7', 'FAS']):
                        return 'Germinal Center B Cell'
                    if any(seg in ['gc', 'gl7', 'fas'] for seg in [p.strip().lower() for p in gate_lower.split('/') if p.strip()]):
                        return 'Germinal Center B Cell'
                    if 'CD27' in marker_upper:
                        return 'Memory B Cell'
                    if 'IGD' in marker_upper:
                        return 'Naive B Cell'

        return None

    def get_full_classification(self, gate_path: str) -> Dict[str, any]:
        """Return lineage, subset, confidence, and evidence for a gate path."""
        lineage_info = self.classify_cell_lineage(gate_path)
        lineage = lineage_info['lineage']

        subset = self.classify_cell_subset(gate_path, lineage)

        if subset:
            description = subset
        elif lineage != 'Unknown':
            description = lineage
        else:

            parts = gate_path.split('/')
            description = parts[-1] if parts else 'Unknown Cell Type'

        return {
            'lineage': lineage,
            'subset': subset,
            'description': description,
            'confidence': lineage_info['confidence'],
            'evidence': lineage_info['evidence']
        }

def test_classifier():
    classifier = CellTypeClassifier()

    test_cases = [

        "Singlets/Live/CD3+/CD4+/Tconv",
        "Singlets/Live/CD3+/CD4+/CD25+/Foxp3+",
        "Singlets/Live/CD3+/CD8+",
        "Singlets/Live/CD3+/CD4+/CXCR5+/PD1+",

        "Singlets/Live/CD19+/IgD+",
        "Singlets/Live/CD19+/CD27+",
        "Singlets/Live/CD19+/CD38+/CD138+",
        "Singlets/Live/CD20+/GL7+/Fas+",

        "Singlets/Live/CD3-/CD56+",
        "Singlets/Live/CD3-/NK1.1+",

        "Singlets/Live/CD3-/CD19-/CD56+",
        "Singlets/Live/CD4-/CD19+/CD20+",
    ]

    print("🧪 Testing Cell Type Classifier")
    print("=" * 80)

    for gate_path in test_cases:
        result = classifier.get_full_classification(gate_path)
        print(f"\n📍 {gate_path}")
        print(f"   Lineage: {result['lineage']} (confidence: {result['confidence']})")
        if result['subset']:
            print(f"   Subset: {result['subset']}")
        print(f"   Description: {result['description']}")
        if result['evidence']:
            print(f"   Evidence: {', '.join(result['evidence'][:2])}")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_classifier()
