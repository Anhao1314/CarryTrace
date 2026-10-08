#!/usr/bin/env python3
"""Deterministic CarryTrace vector assets. Decorative motion is not an experiment."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def hero(dark=False, animated=False):
    bg, ink, soft, line = ('#142035', '#f4f5ef', '#a9b6c8', '#34435a') if dark else ('#f6f5ee', '#182b49', '#526176', '#d5dcde')
    panel = '#1d2e46' if dark else '#e6ede6'
    accent = '#c2f586' if dark else '#385dba'
    motion = '''<style>@keyframes travel{0%{stroke-dashoffset:280}100%{stroke-dashoffset:0}}.trace{stroke-dasharray:280;animation:travel 4.6s ease-out 1}@media(prefers-reduced-motion:reduce){.trace{animation:none}}</style>''' if animated else ''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 358" role="img" aria-labelledby="title desc">
<title id="title">CarryTrace. Your work continues.</title>
<desc id="desc">The continuity skill for AI agents. Keep decisions, trace evidence, continue work. Decorative illustration, not measured task performance.</desc>
{motion}
<rect x="1" y="1" width="958" height="356" rx="22" fill="{bg}" stroke="{line}"/>
<g font-family="Arial, Helvetica, sans-serif">
<text x="40" y="43" font-size="12" font-weight="700" letter-spacing="2" fill="{soft}">AI AGENT / CONTINUITY SKILL</text>
<rect x="791" y="22" width="128" height="30" rx="15" fill="{panel}"/>
<circle cx="809" cy="37" r="4" fill="{accent}"/>
<text x="822" y="41" font-size="11" font-weight="700" letter-spacing="1" fill="{ink}">LOCAL FIRST</text>
<text x="37" y="146" font-size="78" font-weight="800" letter-spacing="-4" fill="{ink}">CarryTrace<tspan fill="{accent}">.</tspan></text>
<path d="M43 166 Q182 179 328 166" fill="none" stroke="#b9e780" stroke-width="7" stroke-linecap="round"/>
<text x="40" y="217" font-size="30" font-weight="700" letter-spacing="-.5" fill="{ink}">Your work continues.</text>
<text x="40" y="250" font-size="17" fill="{soft}">Keep the decisions. Bring the evidence.</text>
<line x1="40" y1="291" x2="920" y2="291" stroke="{line}"/>
<text x="40" y="324" font-size="11" font-weight="700" letter-spacing="1.4" fill="{soft}">FORMERLY CHAT-DISTILLER</text>
<text x="588" y="324" font-size="11" font-weight="700" letter-spacing="1.1" fill="{soft}">DECISIONS / EVIDENCE / NEXT STEPS</text>
<rect x="682" y="90" width="194" height="164" rx="28" fill="{panel}" transform="rotate(7 779 172)"/>
<path d="M807 121 C774 90 718 109 718 157 C718 210 775 225 814 196" stroke="{ink}" stroke-width="13" stroke-linecap="round" fill="none"/>
<path class="trace" d="M731 175 C774 206 834 171 816 145 M794 151 L816 134 L835 153" stroke="{accent}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
<circle cx="728" cy="173" r="6" fill="#67cfe7"/>
<path d="M902 120V141M892 130H913M662 225L672 237M661 238L674 225" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>
<circle cx="672" cy="102" r="4" fill="#67cfe7"/>
</g>
</svg>
'''


def build():
    output = {}
    for dark, mode in ((False, 'light'), (True, 'dark')):
        for animated in (False, True):
            suffix = '' if animated else '-static'
            output[f'assets/brand/hero-{mode}{suffix}.svg'] = hero(dark, animated)
    output['assets/brand/mark.svg'] = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" aria-label="CarryTrace mark: a continuous trace">
<rect x="2" y="2" width="92" height="92" rx="25" fill="#142035"/>
<path d="M63 24C40 6 17 25 19 49C20 72 44 84 65 68" fill="none" stroke="#c2f586" stroke-width="9" stroke-linecap="round"/>
<path d="M34 54C51 69 74 55 69 39M58 38L69 29L79 42" fill="none" stroke="#67cfe7" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
'''
    return output


def main():
    p = argparse.ArgumentParser(); p.add_argument('--check', action='store_true'); a = p.parse_args()
    for name, body in build().items():
        target = ROOT / name
        if a.check:
            if not target.is_file() or target.read_text(encoding='utf-8') != body:
                raise SystemExit('brand asset differs from generator: ' + name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding='utf-8')
    print('CarryTrace brand assets: 5 checked' if a.check else 'CarryTrace brand assets: 5 written')


if __name__ == '__main__':
    main()
