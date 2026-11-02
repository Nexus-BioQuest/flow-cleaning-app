#!/usr/bin/env python3
"""Rule-based display names for flow cytometry gates and metrics."""

import re
from typing import Dict, List, Tuple, Optional
import pandas as pd

class SmartGateNamer:
    """Apply deterministic rules to gate and metric display names."""

    def __init__(self):
        # Cell-type display-name mappings.
        self.cell_type_map = {
            'Total_CD4': 'Total CD4+',
            'Total_CD4_T_Cells': 'Total CD4 T Cells',
            'Total_CD8': 'Total CD8+',
            'Total_CD8_T_Cells': 'Total CD8 T Cells',
            'Total_B_Cells': 'Total B',
            'Proliferated': 'Proliferating',
            'Proliferated-': 'Non-Proliferating',
            'CD19_pos': 'Total B',
            'Tconv': 'Tconv',
            'GC-Tfh': 'GC-Tfh',
            'mTfh': 'mTfh',
            'Tfh': 'Tfh',
            'TfH': 'TfH',
            'NK_Cells': 'NK',
            'Total_B-cells_CD20-CD19': 'Total B',
            'Pre_GC': 'Pre-GC B',
            'Pre-GC': 'Pre-GC B',
            'PreGC': 'Pre-GC B',
            'GC': 'GC B',
            'Memory': 'Memory B',
            'Naive': 'Naïve B',
            'Plasmablasts_Cells': 'Plasmablasts + Plasma',
            'Plasma_cells': 'Plasma',
            'Plasmablasts': 'Plasmablasts',
            'CD4_TEM': 'CD4+ TEM',
            'CD8_TEM': 'CD8+ TEM',

            'CD4_central_memory': 'CD4+ Central Memory',
            'CD4_effector_memory': 'CD4+ Effector Memory',
            'CD4_naive': 'CD4+ Naive',
            'CD8_central_memory': 'CD8+ Central Memory',
            'CD8_effector_memory': 'CD8+ Effector Memory',
            'CD8_naive': 'CD8+ Naive',
            'central_memory': 'Central Memory',
            'effector_memory': 'Effector Memory',
            'naive': 'Naive',

            'CD4_prolif': 'CD4+ Proliferating',
            'CD8_prolif': 'CD8+ Proliferating',
            'prolif': 'Proliferating',

            'CD45_pos_viable': 'CD45+ Viable',
            'viable': 'Viable',

            'CD4+': 'CD4+',
            'CD4_pos': 'CD4+',
            'CD8+': 'CD8+',
            'CD8_pos': 'CD8+',
            'CD4-': 'CD4-',
            'CD19-': 'CD19-',
            'Live': 'Viable',
        }

        # Marker mappings for frequency labels.
        self.marker_map = {
            'CD19+': 'CD19+',
            'CD19_pos': 'CD19+',
            'CD38+': 'CD38+',
            'CD38_pos': 'CD38+',
            'CD86+': 'CD86+',
            'CD86_pos': 'CD86+',
            'CD86pos': 'CD86+',
            'CD20+': 'CD20+',
            'CD20_pos': 'CD20+',
            'CD267+': 'CD267+',
            'CD267_pos': 'CD267+',
            'CD11c+': 'CD11c+',
            'CD11c_pos': 'CD11c+',
            'LILBR1_pos': 'LILRB1+',
            'LILRB1_pos': 'LILRB1+',
            'CXCR5_pos': 'CXCR5+',
            'OX40L_pos': 'OX40L+',
            'CD25_pos': 'CD25+',
            'ICOS_pos': 'ICOS+',
            'CTLA4_pos_PD1_neg': 'CTLA4+PD1-',
            'CTLA4_pos_PD1_pos': 'CTLA4+PD1+',
            'CTLA4_neg_PD1_neg': 'CTLA4-PD1-',
            'CTLA4_neg_PD1_pos': 'CTLA4-PD1+',
            'PD1_pos': 'PD1+ Tconv',
            'PD1_neg': 'PD1- Tconv',
        }

        # Fluorophore-to-marker mappings for MFI labels.
        self.fluorophore_map = {
            'BB700_CD19-H': 'CD19',
            'BV480_CD20-H': 'CD20',
            'BV605_CD86-H': 'CD86',
            'PE-Cy7_CD11c-H': 'CD11c',
            'PE_CD267-H': 'CD267',
            'APC_CD38-H': 'CD38',
            'Comp-CD86_BV605-H': 'CD86',
            'Comp-LILBR1_PE-H': 'LILRB1',
            'Comp-PE_OX40L-H': 'OX40L',
            'Comp-AF488_ICOS-H': 'ICOS',
            'Comp-APC_CD38-H': 'CD38',
            'Comp-BV650_CD25-H': 'CD25',
            'Comp-PE_Cy7_PD-1-H': 'PD-1',
            'Comp-PE_Cy7_PD_1-H': 'PD-1',
            'Comp-PE_Cy7_PD1-H': 'PD-1',
            'Comp-PE_CTLA4-H': 'CTLA4',
            'Comp-PE-Cy7_PD1-H': 'PD-1',
            'Comp-BUV496_CD86-H': 'CD86',
            'Comp-PE-Cy7_PD1-A': 'PD-1',
            'Comp-PE_CTLA4-A': 'CTLA4',
        }

        # Special-case mappings.
        self.special_cases = {
            'Singlets': 'N/A',
            'Beads': 'N/A',
            'Singlets/Beads': 'N/A',
            'Singlets/beads': 'N/A',
            'Singlets/Scatter': 'N/A',
            'singlets': 'N/A',
            'beads': 'N/A',
            'singlets/beads': 'N/A',
            'singlets/beads': 'N/A',
            'singlets/scatter': 'N/A',
            'Singlets/scatter': 'N/A'
        }

    def _is_prolif_gate(self, gate_name: str) -> bool:
        """Return whether a gate denotes positive proliferation."""
        if not gate_name:
            return False
        if gate_name.rstrip().endswith('-'):
            return False
        return any(x in gate_name.lower() for x in ['prolif', 'proliferat'])

    def _is_non_prolif_gate(self, gate_name: str) -> bool:
        """Return whether a gate denotes non-proliferation."""
        if not gate_name:
            return False
        return (any(x in gate_name.lower() for x in ['prolif', 'proliferat'])
                and gate_name.rstrip().endswith('-'))

    def _get_non_proliferating_display(self, parts: List[str], context: str = "Cells") -> str:
        """Format a non-proliferating gate with its parent cell type."""
        last_gate = parts[-1] if parts else ''
        parent_gate = parts[-2] if len(parts) >= 2 else None
        grandparent_gate = parts[-3] if len(parts) >= 3 else None

        if self._is_non_prolif_gate(last_gate):
            parent_cell = self._lookup_cell_type(parent_gate) if parent_gate else None
        elif parent_gate and self._is_non_prolif_gate(parent_gate):
            parent_cell = self._lookup_cell_type(grandparent_gate)
        else:
            parent_cell = None

        if not parent_cell:
            return "Non-Proliferating"

        suffix = f" {context}" if context and not parent_cell.endswith(context) else ""
        return f"Non-Proliferating {parent_cell}{suffix}"

    def _get_proliferating_display(self, parts: List[str], context: str = "Cells") -> str:
        """Format a proliferating gate with its parent or grandparent cell type."""
        last_gate = parts[-1] if parts else ''
        parent_gate = parts[-2] if len(parts) >= 2 else None
        grandparent_gate = parts[-3] if len(parts) >= 3 else None

        if self._is_prolif_gate(last_gate):
            parent_cell = self._lookup_cell_type(parent_gate) if parent_gate else None

        elif parent_gate and self._is_prolif_gate(parent_gate):
            parent_cell = self._lookup_cell_type(grandparent_gate)
        else:
            parent_cell = None

        if not parent_cell:
            return "Proliferating"

        if parent_gate == 'Plasmablasts_Cells':
            return "Proliferating Plasmablasts + Plasma"
        elif parent_gate == 'Plasmablasts':

            return f"Proliferating {parent_cell}"
        elif parent_gate == 'Plasma_cells':

            if context:
                return f"Proliferating {parent_cell} {context}"
            else:
                return f"Proliferating {parent_cell}"
        else:
            suffix = f" {context}" if context and not parent_cell.endswith(context) else ""
            return f"Proliferating {parent_cell}{suffix}"

    def _get_marker_status_display(self, gate_name: str, full_gate_path: str = "") -> Optional[str]:
        """Format marker-positive or negative gates, using the path to disambiguate CD19."""

        gate_name_clean = gate_name.split('/')[-1] if '/' in gate_name else gate_name

        compact_markers = re.findall(
            r'((?:CD\d+|CTLA4|PD_?1|[A-Z][a-z]*\d*?))(?:[_\s-]*)(pos|neg|positive|negative)',
            gate_name_clean,
            flags=re.IGNORECASE,
        )
        compact_text = ''.join(gate_name_clean.split()).casefold()
        compact_source = re.sub(r'[_\s-]+', '', gate_name_clean).casefold()
        if compact_markers and ''.join(f"{marker}{status}" for marker, status in compact_markers).casefold() == compact_source:
            marker_display = [
                f"{self._canonical_marker(marker)}{'+' if 'pos' in status.lower() else '-'}"
                for marker, status in compact_markers
            ]
            return ''.join(marker_display) if len(marker_display) > 1 else marker_display[0]

        # Accept common FlowJo variants, including CD86 positive, CD86_pos,

        generic = re.fullmatch(
            r'\s*([A-Za-z][A-Za-z0-9_-]*?)\s*(?:[_\s-]*(pos(?:itive)?|neg(?:ative)?)|([+\-⁺⁻]))\s*',
            gate_name_clean,
            flags=re.IGNORECASE,
        )
        if generic:
            marker = self._canonical_marker(generic.group(1))
            status = generic.group(2) or generic.group(3)
            sign = '+' if str(status).lower().startswith('pos') or status in {'+', '⁺'} else '-'
            return f"{marker}{sign}"

        for marker_key, marker_display in self.marker_map.items():
            # Require explicit positive CD19 status to avoid matching negated or composite gate names.
            if 'CD19' in marker_key:
                # Match explicit positive CD19 status in the gate name only.

                if not (gate_name_clean.lower() in ['cd19+', 'cd19_pos', 'cd19-', 'cd19_neg']):
                    continue

            if marker_key.lower() in gate_name_clean.lower():

                base_marker = marker_display.rstrip('+--').strip()

                if re.search(r'(_pos|_positive|\+)$', gate_name_clean, re.IGNORECASE):
                    return f"{base_marker}+"
                elif re.search(r'(_neg|_negative|-|-)$', gate_name_clean, re.IGNORECASE):
                    return f"{base_marker}-"
                else:
                    return base_marker
        return None

    @staticmethod
    def _canonical_marker(value: str) -> str:
        """Normalize spelling without changing the identity of an unknown marker."""
        compact = re.sub(r'[\s_]+', '', str(value)).replace('–', '-').replace('−', '-')
        aliases = {
            'pd1': 'PD-1', 'pd-1': 'PD-1', 'ctla4': 'CTLA4', 'ctla-4': 'CTLA4',
            'lilbr1': 'LILRB1', 'lilrb1': 'LILRB1', 'hladr': 'HLA-DR',
            'hla-dr': 'HLA-DR', 'ox40l': 'OX40L', 'ox40': 'OX40',
        }
        lower = compact.lower()
        if lower.startswith('totalctla4'):
            return 'Total CTLA4'
        if lower.startswith('totalpd1') or lower.startswith('totalpd-1'):
            return 'Total PD-1'
        if lower in aliases:
            return aliases[lower]
        match = re.fullmatch(r'cd(\d+)([a-z]?)', lower)
        if match:
            return f"CD{match.group(1)}{match.group(2)}"
        match = re.fullmatch(r'(cxcr|ccr)(\d+)', lower)
        if match:
            return f"{match.group(1).upper()}{match.group(2)}"
        if re.fullmatch(r'ig[admeg]', lower):
            return f"Ig{lower[-1].upper()}"
        return compact

    @staticmethod
    def _canonical_metric(metric: str) -> str:
        text = re.sub(r'\s+', ' ', str(metric or '')).strip()
        normalized = re.sub(r'[^a-z0-9]+', ' ', text.casefold()).strip()
        if normalized in {'count', 'counts', 'event count', 'event counts'}:
            return 'Count'
        if re.match(r'^(freq|frequency)( of)? grand ?parent', normalized):
            return 'Freq. of Grandparent'
        if re.match(r'^(freq|frequency)( of)? parent', normalized):
            return 'Freq. of Parent'
        if re.match(r'^(freq|frequency)( of)? live( cd45( positive| pos)?)?', normalized):
            return 'Freq. of Live CD45+' if 'cd45' in normalized else 'Freq. of Live'
        if re.match(r'^(freq|frequency)( of)? total cd4 t cells?$', normalized):
            return 'Freq. of Total CD4 T Cells'
        if re.match(r'^(freq|frequency)( of)? total cd8 t cells?$', normalized):
            return 'Freq. of Total CD8 T Cells'
        if normalized.startswith(('median ', 'mfi ')):
            channel = re.search(r'\(([^)]+)\)', text)
            return f"Median ({channel.group(1).strip()})" if channel else text
        return text

    def generate_name(self, gate_path: str, metric: str) -> str:
        """Build a display name from a gate path and metric."""
        gate_path = str(gate_path or '').strip().strip('/')
        metric = self._canonical_metric(metric)
        if gate_path in self.special_cases:
            return 'Not Applicable'
        if gate_path == 'Singlets/Scatter/Live' and metric == 'Freq. of Parent':
            return 'Viable %'

        if metric == 'Count':
            result = self._generate_count_name(gate_path)
        elif metric == 'Freq. of Parent':
            result = self._generate_freq_parent_name(gate_path)
        elif metric == 'Freq. of Grandparent':
            result = self._generate_freq_grandparent_name(gate_path)
        elif metric == 'Freq. of Live' or metric == 'Freq. of Live CD45+':
            result = self._generate_freq_live_name(gate_path)
        elif metric == 'Freq. of Total_B-cells_CD20-CD19':
            result = self._generate_freq_custom_parent_name(gate_path, 'Total B Cells')
        elif metric == 'Freq. of Total CD4 T Cells':
            result = self._generate_freq_custom_parent_name(gate_path, 'Total CD4 T Cells')
        elif metric == 'Freq. of Total CD8 T Cells':
            result = self._generate_freq_custom_parent_name(gate_path, 'Total CD8 T Cells')
        elif metric.startswith('Median'):
            result = self._generate_median_name(gate_path, metric)
        else:
            result = f"Unknown metric: {metric}"

        return self._apply_title_case(result)

    def _generate_count_name(self, gate_path: str) -> str:
        parts = [p for p in gate_path.split('/') if p]
        if not parts:
            return ''

        last_gate = parts[-1]
        last_gate_lower = last_gate.lower()

        marker_display = self._get_marker_status_display(last_gate, gate_path)

        if marker_display:
            parent_gate = parts[-2] if len(parts) >= 2 else None
            parent_marker_display = None
            if parent_gate:
                parent_marker_display = self._get_marker_status_display(parent_gate, gate_path)

            if parent_marker_display:
                return f"{marker_display} {parent_marker_display} Cell Count"

            parent_cell = self._lookup_cell_type(parent_gate)

            if parent_cell in ['Total CD4 T Cells', 'Total CD8 T Cells']:
                return f"{marker_display} {parent_cell} Count"
            else:
                return f"{marker_display} {parent_cell} Cell Count"

        if self._is_prolif_gate(last_gate):
            prolif_display = self._get_proliferating_display(parts, context="")

            parent_gate = parts[-2] if len(parts) >= 2 else None

            if parent_gate == 'Plasmablasts_Cells':
                return "Proliferating Plasmablasts + Plasma Cell Count"
            elif parent_gate == 'Plasmablasts':
                return f"{prolif_display} Count"
            elif parent_gate in ['Total_CD4_T_Cells', 'Total_CD8_T_Cells']:

                parent_cell = self._lookup_cell_type(parent_gate)
                parent_singular = parent_cell.replace(' T Cells', ' T Cell')
                return f"Proliferating {parent_singular} Count"
            else:
                return f"{prolif_display} Cell Count"

        if self._is_non_prolif_gate(last_gate):
            non_prolif_display = self._get_non_proliferating_display(parts, context="")
            parent_gate = parts[-2] if len(parts) >= 2 else None
            if parent_gate in ['Total_CD4_T_Cells', 'Total_CD8_T_Cells']:
                parent_cell = self._lookup_cell_type(parent_gate)
                parent_singular = parent_cell.replace(' T Cells', ' T Cell')
                return f"Non-Proliferating {parent_singular} Count"
            else:
                return f"{non_prolif_display} Cell Count"

        cell_type = self._lookup_cell_type(last_gate)

        use_count_only = ['Plasmablasts']

        if last_gate == 'Plasmablasts_Cells':
            return "Plasmablasts + Plasma Cells Count"
        elif cell_type in use_count_only:
            return f"{cell_type} Count"
        elif cell_type in ['Total CD4 T Cells', 'Total CD8 T Cells']:

            return cell_type.replace(' T Cells', ' T Cell Count')
        else:

            return f"{cell_type} Cell Count"

    def _generate_freq_parent_name(self, gate_path: str) -> str:
        parts = [p for p in gate_path.split('/') if p]
        current_gate = parts[-1]
        parent_gate = parts[-2] if len(parts) >= 2 else None
        grandparent_gate = parts[-3] if len(parts) >= 3 else None

        marker_display = self._get_marker_status_display(current_gate, gate_path)

        is_under_prolif = parent_gate and self._is_prolif_gate(parent_gate)
        is_under_non_prolif = parent_gate and self._is_non_prolif_gate(parent_gate)

        if marker_display:

            if is_under_prolif:

                if grandparent_gate:
                    grandparent_cell = self._get_display_name_for_freq(grandparent_gate)
                    return f"{marker_display} % (of Proliferating {grandparent_cell})"
                else:
                    return f"{marker_display} % (of Proliferating)"
            elif is_under_non_prolif:
                if grandparent_gate:
                    grandparent_cell = self._get_display_name_for_freq(grandparent_gate)
                    return f"{marker_display} % (of Non-Proliferating {grandparent_cell})"
                else:
                    return f"{marker_display} % (of Non-Proliferating)"
            else:

                parent_cell = self._get_display_name_for_freq(parent_gate)
                return f"{marker_display} % (of {parent_cell})"

        if self._is_prolif_gate(current_gate):
            parent_cell = self._get_display_name_for_freq(parent_gate)
            return f"Proliferating % (of {parent_cell})"

        if is_under_prolif:
            current_cell = self._get_display_name_for_freq(current_gate)
            if grandparent_gate:
                grandparent_cell = self._get_display_name_for_freq(grandparent_gate)
                return f"{current_cell} % (of Proliferating {grandparent_cell})"
            else:
                return f"{current_cell} % (of Proliferating)"
        elif is_under_non_prolif:
            current_cell = self._get_display_name_for_freq(current_gate)
            if grandparent_gate:
                grandparent_cell = self._get_display_name_for_freq(grandparent_gate)
                return f"{current_cell} % (of Non-Proliferating {grandparent_cell})"
            else:
                return f"{current_cell} % (of Non-Proliferating)"

        parent_cell = self._get_display_name_for_freq(parent_gate)
        current_cell = self._get_display_name_for_freq(current_gate)
        return f"{current_cell} % (of {parent_cell})"

    def _generate_freq_grandparent_name(self, gate_path: str) -> str:
        """Format a gate frequency relative to its grandparent gate."""
        parts = [p for p in gate_path.split('/') if p]

        if len(parts) < 3:

            return self._generate_freq_parent_name(gate_path)

        current_gate = parts[-1]
        parent_gate = parts[-2]
        grandparent_gate = parts[-3]
        great_grandparent_gate = parts[-4] if len(parts) >= 4 else None

        marker_display = self._get_marker_status_display(current_gate, gate_path)

        is_under_prolif = parent_gate and self._is_prolif_gate(parent_gate)

        if marker_display:

            if is_under_prolif:

                if great_grandparent_gate:
                    great_grandparent_cell = self._get_display_name_for_freq(great_grandparent_gate)
                    return f"{marker_display} % (of Proliferating {great_grandparent_cell})"
                else:

                    grandparent_cell = self._get_display_name_for_freq(grandparent_gate)
                    return f"{marker_display} % (of Proliferating {grandparent_cell})"
            else:

                grandparent_cell = self._get_display_name_for_freq(grandparent_gate)
                return f"{marker_display} % (of {grandparent_cell})"

        if self._is_prolif_gate(current_gate):
            grandparent_cell = self._get_display_name_for_freq(grandparent_gate)
            return f"Proliferating % (of {grandparent_cell})"

        grandparent_cell = self._get_display_name_for_freq(grandparent_gate)
        current_cell = self._get_display_name_for_freq(current_gate)
        return f"{current_cell} % (of {grandparent_cell})"

    def _generate_freq_live_name(self, gate_path: str) -> str:
        parts = [p for p in gate_path.split('/') if p]
        last_gate = parts[-1]
        cell_type = self._get_display_name_for_freq(last_gate)
        if self._is_prolif_gate(last_gate):
            prolif_label = self._get_proliferating_display(parts)
            return f"{prolif_label} % (of Viable)"
        if self._is_non_prolif_gate(last_gate):
            non_prolif_label = self._get_non_proliferating_display(parts)
            return f"{non_prolif_label} % (of Viable)"

        return f"{cell_type} % (of Viable)"

    def _generate_freq_custom_parent_name(self, gate_path: str, custom_parent: str) -> str:
        parts = [p for p in gate_path.split('/') if p]
        current_gate = parts[-1]
        current_cell = self._get_display_name_for_freq(current_gate)
        return f"{current_cell} % (of {custom_parent})"

    def _generate_median_name(self, gate_path: str, metric: str) -> str:
        parts = [p for p in gate_path.split('/') if p]
        metric_clean = re.sub(r'\s*::\s*\w+', '', metric)
        match = re.search(r'Median \(([^)]+)\)', metric_clean)

        if match:
            fluorophore = match.group(1).strip()
            marker_match = re.search(
                r'(CD\s*\d{1,3}[a-z]?|PD[-_ ]?1|LILR[AB]\s*\d+|CXCR\s*\d+|CCR\s*\d+|HLA[-_ ]?DR|ICOS|CTLA[-_ ]?4|OX40L?|Ig[ADMEG])',
                fluorophore,
                flags=re.IGNORECASE,
            )
            if 'LILBR1' in fluorophore or 'LILRB1' in fluorophore:
                marker = 'LILRB1'
            elif marker_match:
                marker = self._canonical_marker(marker_match.group(1))
            else:
                compact = re.sub(r'[^a-z0-9]', '', fluorophore.casefold())
                marker = next((value for key, value in self.fluorophore_map.items()
                               if re.sub(r'[^a-z0-9]', '', key.casefold()) == compact), None)
                # Dye-only channels are not mapped to a biological marker.
                marker = marker or re.sub(r'^(comp[-_ ]*)', '', fluorophore, flags=re.IGNORECASE)
        else:
            marker = "Unknown"

        last_gate = parts[-1]
        parent_gate = parts[-2] if len(parts) >= 2 else None

        marker_display = self._get_marker_status_display(last_gate, gate_path)
        is_under_prolif = parent_gate and self._is_prolif_gate(parent_gate)
        is_under_non_prolif = parent_gate and self._is_non_prolif_gate(parent_gate)
        grandparent_gate = parts[-3] if len(parts) >= 3 else None

        if marker_display:
            if is_under_prolif:
                if grandparent_gate:
                    grandparent_cell = self._get_display_name_for_mfi(grandparent_gate)
                    return f"{marker} MFI ({marker_display} Proliferating {grandparent_cell})"
                return f"{marker} MFI ({marker_display} Proliferating)"
            elif is_under_non_prolif:
                if grandparent_gate:
                    grandparent_cell = self._get_display_name_for_mfi(grandparent_gate)
                    return f"{marker} MFI ({marker_display} Non-Proliferating {grandparent_cell})"
                return f"{marker} MFI ({marker_display} Non-Proliferating)"
            parent_cell = self._get_display_name_for_mfi(parent_gate)
            if parent_cell:
                return f"{marker} MFI ({marker_display} {parent_cell})"
            return f"{marker} MFI ({marker_display})"

        if self._is_prolif_gate(last_gate):
            prolif_label = self._get_proliferating_display(parts, context="Cells")
            return f"{marker} MFI ({prolif_label})"

        if self._is_non_prolif_gate(last_gate):
            parent_cell = self._get_display_name_for_mfi(parent_gate)
            if parent_cell:
                return f"{marker} MFI (Non-Proliferating {parent_cell})"
            return f"{marker} MFI (Non-Proliferating)"

        cell_type = self._get_display_name_for_mfi(last_gate)
        if is_under_prolif:
            if grandparent_gate:
                grandparent_cell = self._get_display_name_for_mfi(grandparent_gate)
                return f"{marker} MFI ({cell_type} Proliferating {grandparent_cell})"
            return f"{marker} MFI ({cell_type} Proliferating)"
        elif is_under_non_prolif:
            if grandparent_gate:
                grandparent_cell = self._get_display_name_for_mfi(grandparent_gate)
                return f"{marker} MFI ({cell_type} Non-Proliferating {grandparent_cell})"
            return f"{marker} MFI ({cell_type} Non-Proliferating)"
        return f"{marker} MFI ({cell_type})"

    def _lookup_cell_type(self, gate_name: str) -> str:
        """Resolve a gate name to a display label."""
        if not gate_name:
            return ''
        gate_clean = gate_name.strip('/')

        if gate_clean in self.cell_type_map:
            return self.cell_type_map[gate_clean]

        gate_lower = gate_clean.lower()

        def normalize_for_matching(text: str) -> str:
            return re.sub(r'[^a-z0-9\+\-]+', ' ', text.lower()).strip()

        normalized_gate = normalize_for_matching(gate_clean)
        gate_tokens = normalized_gate.split()

        for key, value in self.cell_type_map.items():
            normalized_key = normalize_for_matching(key)
            if normalized_key == normalized_gate:
                return value

        # Whole-token matching prevents partial key collisions.
        for key, value in self.cell_type_map.items():
            normalized_key = normalize_for_matching(key)
            if not normalized_key:
                continue
            key_tokens = normalized_key.split()
            if key_tokens == gate_tokens:
                return value
            if len(key_tokens) <= len(gate_tokens) and all(token in gate_tokens for token in key_tokens):
                return value

        compact_markers = re.findall(
            r'((?:CD\d+|[A-Z][a-z]*\d*?))(pos|neg|positive|negative)',
            gate_clean,
            flags=re.IGNORECASE
        )
        if compact_markers:
            marker_parts = [
                f"{self._canonical_marker(marker)}{'+' if 'pos' in status.lower() else '-'}"
                for marker, status in compact_markers
            ]
            return ' '.join(marker_parts)

        def replace_marker(match):
            marker = match.group(1).upper()
            status_text = match.group(2).lower()
            status = '+' if 'pos' in status_text else '-'
            return f"{marker}{status}"

        result = re.sub(r'([A-Za-z]+\d*)_(pos|neg|positive|negative)', replace_marker, gate_clean, flags=re.IGNORECASE)

        result = result.replace('_', ' ')
        result = re.sub(r'(?<![A-Z\d])-(?![+\-])|(?<![\w\d])-(?=\w)', ' ', result)

        preserve_upper = {"OX40", "OX40l", "PD1", "CTLA4", "CD8"}

        words = result.split()
        processed_words = []
        for word in words:
            if re.match(r'^[A-Z]{2,}\d*[\+\-]$', word) or word.upper() in preserve_upper:
                processed_words.append(word.upper())

            elif 'cd8' in word.lower():
                processed_words.append(word.replace('cd8', 'CD8').replace('Cd8', 'CD8').replace('CD8', 'CD8'))
            else:
                processed_words.append(word.capitalize())

        return ' '.join(processed_words)

    def _get_display_name_for_freq(self, gate_name: str) -> str:
        if not gate_name:
            return ''
        base_name = self._lookup_cell_type(gate_name)

        needs_cells = ['GC B', 'Memory B', 'Naïve B', 'Pre-GC B', 'NK', 'Total B', 'Plasma', 
                       'Tconv', 'Tfh', 'mTfh', 'GC-Tfh', 'PD1+ Tconv', 'PD1- Tconv']

        no_cells = ['Total CD4 T Cells', 'Total CD8 T Cells', 'Total CD4+', 'Total CD4', 
                    'CD4+', 'CD4-', 'CD19-', 'Viable', 'Plasmablasts']

        if base_name == 'Total CD4+':
            return 'Total CD4'
        if base_name == 'Total CD4 T Cells':
            return 'Total CD4 T Cells'
        if base_name == 'Total CD8 T Cells':
            return 'Total CD8 T Cells'
        if base_name in no_cells:
            return base_name
        if any(item in base_name for item in needs_cells) and not base_name.endswith('Cells'):
            return f"{base_name} Cells"
        if base_name == 'Plasmablasts + Plasma':
            return 'Plasmablasts + Plasma Cells'
        return base_name

    def _get_display_name_for_mfi(self, gate_name: str) -> str:
        if not gate_name:
            return ''
        base_name = self._lookup_cell_type(gate_name)

        needs_cells = ['GC B', 'Memory B', 'Naïve B', 'Pre-GC B', 'Total B', 'Plasma',
                       'Tconv', 'Tfh', 'mTfh', 'GC-Tfh', 'PD1+ Tconv', 'PD1- Tconv']

        no_cells = ['Total CD4 T Cells', 'Total CD8 T Cells', 'Total CD4+', 'Plasmablasts']

        if base_name == 'Total CD4+':
            return 'Total CD4'
        if base_name == 'Total CD4 T Cells':
            return 'Total CD4 T Cells'
        if base_name == 'Total CD8 T Cells':
            return 'Total CD8 T Cells'
        if base_name in no_cells:
            return base_name
        if any(item in base_name for item in needs_cells) and not base_name.endswith('Cells'):
            return f"{base_name} Cells"
        if base_name == 'Plasmablasts + Plasma':
            return 'Plasma Blasts + Plasma Cells'
        return base_name

    def _apply_title_case(self, text: str) -> str:
        """
        Apply title case to the text, but preserve:
        - Abbreviations (CD4+, CD8+, GC, MFI, etc.)
        - Markers with + or - (CD19+, LILRB1+, etc.)
        - Proper formatting within parentheses
        """

        preserve_words = {
            'CD4+', 'CD8+', 'CD3+', 'CD19+', 'CD20+', 'CD38+', 'CD86+', 
            'CD267+', 'CD11c+', 'LILRB1+', 'CXCR5+', 'GC', 'MFI', 'NK',
            'CD4', 'CD8', 'CD3', 'CD19', 'CD20', 'CD38', 'CD86', 'CD267',
            'CD11c', 'LILRB1', 'CXCR5', 'Tfh', 'GC-Tfh','mTfh','TfH', 'Tconv', 'IgD', 'IgM', 'IgG',
            'CD4-', 'CD8-', 'CD8','CD3-', 'CD19-', 'CD20-', 'Pre-GC', 'CD4+ TEM', 'CD8+ TEM',
            'OX40', 'OX40L', 'PD-1', 'PD1', 'CTLA4', 'HLA-DR',
            'OX40l','OX40l+', 'OX40L+', 'OX40L_pos'
        }

        small_words = {'of', 'a', 'an', 'the', 'and', 'or', 'but'}

        parts = []
        current_pos = 0

        for match in re.finditer(r'\([^)]+\)', text):

            if match.start() > current_pos:
                before = text[current_pos:match.start()]
                parts.append(self._capitalize_words(before, preserve_words, small_words))

            paren_content = match.group(0)

            inner = paren_content[1:-1]
            processed_inner = self._capitalize_words(inner, preserve_words, small_words, in_parens=True)
            parts.append(f"({processed_inner})")

            current_pos = match.end()

        if current_pos < len(text):
            parts.append(self._capitalize_words(text[current_pos:], preserve_words, small_words))

        return ''.join(parts)

    def _capitalize_words(self, text: str, preserve_words: set, small_words: set, in_parens: bool = False) -> str:
        words = text.split(' ')
        result = []

        for i, word in enumerate(words):

            if not word:
                result.append(word)
                continue

            if word in preserve_words:
                result.append(word)

            elif word.endswith(('+', '-')) or re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9]+)+', word):
                result.append(word)

            elif any(word.startswith(abbr) for abbr in preserve_words):
                result.append(word)

            elif re.match(r'^[A-Z]{2,}\d*[\+\-]?$', word):
                result.append(word)

            elif word.lower() in small_words:
                result.append(word.lower())

            else:
                result.append(word.capitalize())

        return ' '.join(result)

def batch_process_gates(gate_metric_pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    namer = SmartGateNamer()
    results = {}
    for gate_path, metric in gate_metric_pairs:
        key = f"{gate_path} | {metric}"
        results[key] = namer.generate_name(gate_path, metric)
    return results

def create_gate_name_mapping(df: pd.DataFrame, 
                             gate_col: str = 'gate_path',
                             metric_col: str = 'metric') -> pd.DataFrame:
    """Build gate-to-plot mappings with unique display names."""
    namer = SmartGateNamer()

    unique_combos = df[[gate_col, metric_col]].drop_duplicates()

    mappings = []
    seen_lowercase = {}
    seen_sources = {}

    for _, row in unique_combos.iterrows():
        gate_path = row[gate_col]
        metric = row[metric_col]

        original_name = f"{gate_path} | {metric}"
        generated_name = namer.generate_name(gate_path, metric)

        source_key = re.sub(r'\s+', ' ', str(gate_path)).strip().strip('/').casefold()
        name_lower = generated_name.lower()
        if name_lower in seen_lowercase and source_key in seen_sources.get(name_lower, set()):
            final_name = seen_lowercase[name_lower]
        elif name_lower in seen_lowercase:
            path_parts = [part for part in re.split(r'[/\\]', str(gate_path).strip()) if part]
            qualifier_parts = path_parts[-3:] or ["gate"]
            gate_qualifier = " / ".join(qualifier_parts)
            final_name = f"{generated_name} [{gate_qualifier}]"
            if final_name.casefold() in {item['plot_name'].casefold() for item in mappings}:
                final_name = f"{generated_name} [{gate_path}]"
        else:
            final_name = generated_name
            seen_lowercase[name_lower] = generated_name
        seen_sources.setdefault(name_lower, set()).add(source_key)

        mappings.append({
            'original_name': original_name,
            'plot_name': final_name,
            'gate_path': gate_path,
            'metric': metric
        })

    result_df = pd.DataFrame(mappings)

    original_count = len(result_df)
    unique_count = result_df['plot_name'].nunique()

    if original_count != unique_count:
        print(f"Deduplicated: {original_count} original combinations → {unique_count} unique plot names")

    return result_df

if __name__ == "__main__":
    namer = SmartGateNamer()

    test_cases = [
        ("Singlets/Scatter/Live/CD4-/Total_B-cells_CD20-CD19/Plasmablasts_Cells/Plasma_cells/proliferating/CD19+", "Freq. of Parent"),
        ("Singlets/Scatter/Live/CD4-/Total_B-cells_CD20-CD19/Plasmablasts_Cells/Plasma_cells/proliferating/CD20+", "Freq. of Parent"),
        ("Singlets/Scatter/Live/CD4-/Total_B-cells_CD20-CD19/Pre_GC/GC/CD11c+", "Freq. of Grandparent"),
        ("Singlets/Scatter/Live/CD4-/Total_B-cells_CD20-CD19/Pre_GC/GC/proliferating/CD38+", "Freq. of Grandparent"),
    ]

    print("Testing gate naming including frequency of grandparent")
    print("=" * 80)

    for gate_path, metric in test_cases:
        result = namer.generate_name(gate_path, metric)
        print(f"Metric: {metric}")
        print(f"Input:  {gate_path}")
        print(f"Result: {result}")
        print()

    print("=" * 80)
