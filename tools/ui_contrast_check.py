#!/usr/bin/env python3
"""Bounded declared-CSS contrast check for the four informative text selectors returned by QA."""
import json
import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / 'ui/styles.css'


def property_value(css, selector, name):
    blocks = re.findall(r'^' + re.escape(selector) + r'\s*\{([^}]+)\}', css, re.M)
    values = [m.group(1) for block in blocks
              for m in [re.search(r'(?:^|;)\s*' + re.escape(name) + r'\s*:\s*(#[0-9a-fA-F]{3,6})\s*(?:;|$)', block)] if m]
    if len(values) != 1:
        raise ValueError('missing_or_ambiguous_declared_color: ' + selector)
    value = values[0].lower()
    return '#' + ''.join(c * 2 for c in value[1:]) if len(value) == 4 else value


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return sum((c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) * weight
               for c, weight in zip(channels, (0.2126, 0.7152, 0.0722)))


def ratio(foreground, background):
    low, high = sorted((luminance(foreground), luminance(background)))
    return (high + 0.05) / (low + 0.05)


def main():
    css = CSS.read_text()
    # These are the current explicit paint relationships, not a general CSS cascade evaluator.
    # Empty columns are transparent and inherit the root canvas; enabled client rows have a hover paint.
    cases = [('.card-result', '.task-card'), ('.client-contact', '.client-row'),
             ('.client-contact', '.client-row:hover'), ('.client-name small', '.client-row'),
             ('.client-name small', '.client-row:hover'), ('.column-empty', ':root')]
    results = []
    for selector, background_selector in cases:
        foreground = property_value(css, selector, 'color')
        background = property_value(css, background_selector, 'background')
        measured = ratio(foreground, background)
        results.append({'selector': selector, 'background_selector': background_selector,
                        'foreground': foreground, 'background': background,
                        'ratio': round(measured, 3), 'pass': measured >= 4.5})
    passed = all(item['pass'] for item in results)
    print(json.dumps({'scope': 'four_qa_text_selectors_only', 'minimum_ratio': 4.5,
                      'results': results, 'outcome': 'passed' if passed else 'failed'}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
