"""Executive PDF and technical appendix generated entirely on the local host."""
import io
from html import escape
from datetime import datetime, timezone
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from app.analytics import PROFILE, SOURCE


def pdf_report(tenant,scenario,assessment):
    stream=io.BytesIO()
    doc=SimpleDocTemplate(stream,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=46,bottomMargin=42,title='P95 Explorer - Licensing Assessment',author='P95 Explorer')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallNote',fontSize=8,leading=10,textColor=colors.HexColor('#526174'),spaceAfter=8))
    styles.add(ParagraphStyle(name='Banner',fontSize=24,leading=28,textColor=colors.HexColor('#122a38'),spaceAfter=18))
    styles['BodyText'].fontSize=9;styles['BodyText'].leading=12;styles['BodyText'].spaceAfter=7
    styles['Heading2'].fontSize=12;styles['Heading2'].leading=15;styles['Heading2'].spaceBefore=9;styles['Heading2'].spaceAfter=7;styles['Heading2'].keepWithNext=True
    styles['Title'].fontSize=19;styles['Title'].leading=23
    story=[]
    def p(value,style='BodyText'):
        return Paragraph(escape(str(value)),styles[style])
    def table(headers,rows,widths=None):
        cells=[[p(v,'SmallNote') for v in headers]]+[[p(v,'SmallNote') for v in row] for row in rows]
        result=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        result.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e2eee9')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f6f8')]),('BOTTOMPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#bacfc6'))]))
        return result
    def rate(v):return 'Withheld' if v is None else '{:,.1f} Mbps'.format(v)
    def money(v):return 'Not configured' if v is None else '{} {:,.2f}'.format(scenario['commercial']['currency'],v)
    story += [p('P95 Explorer','Banner'),p('Bandwidth licensing assessment','Title'),p(scenario['name'],'Heading2'),p('Workspace: '+tenant+' | Generated '+datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),'SmallNote'),p('Assessment window: '+', '.join(r['month'] for r in assessment['months'])),p('Selected model: '+scenario['model']+' | Rule profile: '+PROFILE)]
    if tenant=='demo' or any('synthetic-demo' in s['source'] for r in assessment['months'] for s in r['sites']):story.append(p('SYNTHETIC DEMO - These observations do not represent a customer tenant.','Heading2'))
    story.append(p('Status: '+('Evidence checks passed; commercial review still required.' if assessment['ready'] else 'Needs review - final recommendations are withheld.'),'Heading2'))
    story.append(table(['Region','Planning capacity','Determining month','Months above capacity'],[(r['region'],rate(r['recommendation']),r['determining_month'] or '-',str(r['months_above'])+' / '+str(r['tested_months'])) for r in assessment['regions']],[110,130,100,171]))
    story += [Spacer(1,14),p('Commercial comparison','Heading2')]
    c=assessment['commercial']
    if c['available']:
        story.append(table(['User-priced option','Modeled term total'],[('Capacity adjusted each modeled month',money(c['total'])),('One expansion sized for the whole term',money(c['true_forward_total'])),('Current capacity plus monthly excess',money(c['true_up_total']))],[285,226]))
        story.append(p(c['note'],'SmallNote'))
        if c['true_up_total'] is None:story.append(p(c['true_up_reason'],'SmallNote'))
        story.append(p('Selected term SKUs: '+ '; '.join((i.get('site') or i['region'])+': '+i['sku']+' ('+rate(i['capacity'])+')' for i in c['selected_skus']),'SmallNote'))
    else:story.append(p(c['reason']))
    story += [p('Assumptions and decisions','Heading2'),p('Growth '+str(scenario['growth'])+'%; headroom '+str(scenario['headroom'])+'%; capacity increment '+str(scenario['increment'])+' Mbps; projection '+str(scenario['horizon'])+' months.'),p('Monthly compounded forecast growth: '+str(scenario['monthly_growth'])+'%.'),p('The capacity increment is user-entered. Actual purchasable SKUs and all monetary rates must be verified against the customer agreement.')]
    for assumption in assessment['assumptions']:story.append(p(assumption,'SmallNote'))
    issues=sorted({w for r in assessment['months'] for w in r['warnings']})
    for issue in issues:story.append(p(issue,'SmallNote'))
    story += [PageBreak(),p('Technical appendix','Title'),p('Observation integrity and sizing evidence','Heading2')]
    for report in assessment['months']:
        story.append(p(report['month']+' - '+('complete observations' if report['complete'] else 'incomplete observations'),'Heading2'))
        story.append(table(['Site / region','Coverage','Complete days','Peak','Site limit plan'],[(s['name']+' / '+s['region'],str(round(s['coverage'],2))+'%',s['complete_days'],rate(s['peak']),rate(s['site_limit_recommendation']) if s['constrained'] else 'Not enforced by scenario') for s in report['sites']],[180,60,65,100,106]))
        for pool in report['pools']:
            story.append(p(pool['region']+': observed '+rate(pool['observed'])+'; determining day '+(pool['determining_day'] or 'none')+'; excluded partial days '+str(pool['excluded_days']),'SmallNote'))
            if pool['contributors']:story.append(p('Daily site P95 contributions: '+', '.join(s['name']+' '+rate(s['mbps']) for s in pool['contributors']),'SmallNote'))
            if pool['cma'] is not None:story.append(p('Supplied CMA '+rate(pool['cma'])+'; reconciliation delta '+rate(pool['reconciliation_delta']),'SmallNote'))
        story.append(Spacer(1,10))
    story += [p('Input provenance','Heading2')]
    if assessment['months']:
        story.append(table(['Site','Observation source','Inventory confirmed'],[(s['name'],s['source'],'Yes' if s['verified'] else 'No') for s in assessment['months'][-1]['sites']],[200,200,111]))
    if scenario['planned_sites']:
        story += [p('Planned site assumptions','Heading2'),table(['Site / region','Starts','Peak','Daily P95'],[(s['name']+' / '+s['region'],s['start'],rate(s['peak']),rate(s['p95'])) for s in scenario['planned_sites']],[210,91,105,105])]
    story += [p('Projection by month','Heading2'),table(['Month','Regional capacity with headroom'],[(f['month'],'; '.join(r['region']+': '+rate(r['recommendation']) for r in f['regions'])) for f in assessment['forecast']],[90,421]),p('Source and interpretation','Heading2'),p(SOURCE,'SmallNote'),p('Cato enforcement reference: https://knowledge.catonetworks.com/docs/managing-site-bandwidth-in-licenses','SmallNote'),p('Bursting is a January 2027 migration scenario. Daily P95 excludes the highest floor(5% of 288) five-minute peaks; the monthly regional calculation uses the largest complete daily sum. Partial days never contribute to the regional result. Classic monthly P95 is educational only.','SmallNote'),p('No API credentials are included. This report may contain customer site names and telemetry summaries. It is an independent planning assessment, not an official Cato quote or certified invoice.','SmallNote')]
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#526174'))
        canvas.drawString(42,23,'P95 Explorer | Independent capacity planning | '+PROFILE)
        canvas.drawRightString(A4[0]-42,23,str(doc.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()
