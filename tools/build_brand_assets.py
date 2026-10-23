#!/usr/bin/env python3
"""Deterministic ClaimLedger vector assets. Decorative motion is not an experiment."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DARK = dict(bg='#0e1626', panel='#17233a', line='#2a3b58', ink='#eef2f7', soft='#9db0c9',
            accent='#63e2a4', sup='#7e8ca3', disp='#e8c268', blue='#6cb8ff')
LIGHT = dict(bg='#f7f5ec', panel='#ffffff', line='#d8dcd2', ink='#16233a', soft='#5d6b80',
             accent='#157f4f', sup='#97a1ac', disp='#a87408', blue='#2b6cb0')


def hero(dark=False, animated=False):
    c = DARK if dark else LIGHT
    motion = ''
    if animated:
        motion = ('<style>@keyframes draw{0%{stroke-dashoffset:260}100%{stroke-dashoffset:0}}'
                  '.bar{stroke-dasharray:260;animation:draw 1.1s ease-out both}'
                  '.b1{animation-delay:.1s}.b2{animation-delay:.4s}.b3{animation-delay:.7s}'
                  '@media(prefers-reduced-motion:reduce){.bar{animation:none}}</style>')
    # The three ledger rows: current (solid green), superseded (struck gray), disputed (dashed amber).
    rows = f'''<rect x="600" y="70" width="320" height="212" rx="20" fill="{c['panel']}" stroke="{c['line']}"/>
<text x="626" y="99" font-size="10" font-weight="700" letter-spacing="1.6" fill="{c['soft']}">TODAY'S BRIEF</text>
<circle cx="632" cy="128" r="6" fill="{c['accent']}"/>
<line class="bar b1" x1="652" y1="128" x2="876" y2="128" stroke="{c['accent']}" stroke-width="8" stroke-linecap="round"/>
<text x="894" y="132" font-size="10" fill="{c['soft']}" font-family="'SFMono-Regular',Consolas,monospace" text-anchor="end">clm_9f2a</text>
<circle cx="632" cy="178" r="6" fill="{c['sup']}"/>
<line class="bar b2" x1="652" y1="178" x2="876" y2="178" stroke="{c['sup']}" stroke-width="8" stroke-linecap="round"/>
<line x1="646" y1="190" x2="882" y2="166" stroke="{c['ink']}" stroke-width="3" stroke-linecap="round" opacity=".85"/>
<text x="894" y="182" font-size="10" fill="{c['soft']}" font-family="'SFMono-Regular',Consolas,monospace" text-anchor="end">clm_4c81</text>
<circle cx="632" cy="228" r="6" fill="{c['disp']}"/>
<line class="bar b3" x1="652" y1="228" x2="876" y2="228" stroke="{c['disp']}" stroke-width="8" stroke-linecap="round" stroke-dasharray="22 12"/>
<text x="894" y="232" font-size="10" fill="{c['soft']}" font-family="'SFMono-Regular',Consolas,monospace" text-anchor="end">clm_b7d3</text>'''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 358" role="img" aria-labelledby="title desc">
<title id="title">ClaimLedger. Your work continues.</title>
<desc id="desc">The decision ledger for AI agents. Claims carry a status: current, superseded or disputed. Decorative illustration, not measured task performance.</desc>
{motion}
<rect x="1" y="1" width="958" height="356" rx="22" fill="{c['bg']}" stroke="{c['line']}"/>
<g font-family="Arial, Helvetica, sans-serif">
<text x="40" y="43" font-size="12" font-weight="700" letter-spacing="2" fill="{c['soft']}">CLAIM LEDGER / THE DECISION LEDGER FOR AI AGENTS</text>
<rect x="762" y="22" width="158" height="30" rx="15" fill="{c['panel']}" stroke="{c['line']}"/>
<circle cx="780" cy="37" r="4" fill="{c['accent']}"/>
<text x="792" y="41" font-size="11" font-weight="700" letter-spacing="1" fill="{c['ink']}">LOCAL · APPEND-ONLY</text>
<text x="37" y="146" font-size="76" font-weight="800" letter-spacing="-3" fill="{c['ink']}">ClaimLedger<tspan fill="{c['accent']}">.</tspan></text>
<text x="40" y="200" font-size="28" font-weight="700" letter-spacing="-.5" fill="{c['ink']}">Your work continues.</text>
<text x="40" y="232" font-size="16" fill="{c['soft']}">Record the decision once. Serve it with status. Never silently stale.</text>
{rows}
<line x1="40" y1="306" x2="920" y2="306" stroke="{c['line']}"/>
<text x="40" y="334" font-size="11" font-weight="700" letter-spacing="1.4" fill="{c['soft']}">FORMERLY CHAT-DISTILLER · CARRYTRACE</text>
<text x="640" y="334" font-size="11" font-weight="700" letter-spacing="1.1" fill="{c['soft']}">CLAIMS / STATUS / BRIEFS</text>
<path d="M560 88l6 6M566 88l-6 6M52 262l6 6M58 262l-6 6" stroke="{c['blue']}" stroke-width="2.4" stroke-linecap="round"/>
</g>
</svg>
'''


def build():
    output = {}
    for dark, mode in ((False, 'light'), (True, 'dark')):
        for animated in (False, True):
            suffix = '' if animated else '-static'
            output[f'assets/brand/hero-{mode}{suffix}.svg'] = hero(dark, animated)
    output['assets/brand/mark.svg'] = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" aria-label="ClaimLedger mark: a three-line ledger — current, superseded, disputed">
<rect x="2" y="2" width="92" height="92" rx="24" fill="{DARK['bg']}"/>
<line x1="26" y1="24" x2="26" y2="72" stroke="{DARK['line']}" stroke-width="3" stroke-linecap="round"/>
<line x1="38" y1="32" x2="78" y2="32" stroke="{DARK['accent']}" stroke-width="7" stroke-linecap="round"/>
<line x1="38" y1="48" x2="78" y2="48" stroke="{DARK['sup']}" stroke-width="7" stroke-linecap="round"/>
<line x1="34" y1="58" x2="82" y2="38" stroke="#eef2f7" stroke-width="2.6" stroke-linecap="round"/>
<line x1="38" y1="64" x2="78" y2="64" stroke="{DARK['disp']}" stroke-width="7" stroke-linecap="round" stroke-dasharray="10 6"/>
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
    print('ClaimLedger brand assets: 5 checked' if a.check else 'ClaimLedger brand assets: 5 written')


if __name__ == '__main__':
    main()
