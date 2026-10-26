"""Detect substantial missing narration using the actual speech transcript."""
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher


def coverage_report(expected, sentences):
    def normalize(text):
        return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())
    source = normalize(expected)
    actual = normalize(' '.join(item['text'] for item in sentences))
    matched = sum(block.size for block in SequenceMatcher(None, source, actual, autojunk=False).get_matching_blocks())
    coverage = matched / max(1, len(source))
    multiset_overlap = sum((Counter(source) & Counter(actual)).values()) / max(1, len(source))
    length_ratio = len(actual) / max(1, len(source))
    minimum = .65 if len(source) < 50 else .45
    passed = bool(actual) and (
        coverage >= minimum
        or (multiset_overlap >= .9 and .85 <= length_ratio <= 1.2)
    )
    return {'sourceCharacters': len(source), 'recognizedCharacters': len(actual),
            'sourceCoverage': round(coverage, 4), 'multisetOverlap': round(multiset_overlap, 4),
            'recognizedLengthRatio': round(length_ratio, 4), 'minimumCoverage': minimum,
            'recognizedText': ' '.join(item['text'] for item in sentences),
            'passed': passed,
            'method': 'ASR transcript character alignment; not a human listening score'}
