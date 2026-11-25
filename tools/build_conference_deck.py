from pathlib import Path
import sys,json,copy,hashlib

from pptx import Presentation
from pptx.util import Inches,Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN
from pptx.enum.chart import XL_CHART_TYPE,XL_LABEL_POSITION,XL_LEGEND_POSITION
from pptx.chart.data import CategoryChartData
from pptx.oxml.xmlchemy import OxmlElement
from PIL import Image
import qrcode

r=Path(__file__).resolve().parents[1]; out=r/'output/presentations';out.mkdir(exist_ok=True)
p=Presentation();p.slide_width= Inches(13.333);p.slide_height=Inches(7.5)
C={'bg':'071017','panel':'0C1620','text':'E8F1F5','muted':'7F93A1','mint':'5EEAD4','amber':'FFB454','red':'FF5C5C'}
def rgb(c):return RGBColor.from_string(C.get(c,c))
def text(container,t,x,y,w,h,size=22,color='text',font='Calibri',bold=False):
    from pptx.shapes.shapetree import SlideShapes
    shapes=container.shapes if hasattr(container.shapes,"add_textbox") else SlideShapes(container.shapes._spTree,container)
    s=shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h));f=s.text_frame;f.word_wrap=True
    f.margin_left=f.margin_right=Inches(.02);f.margin_top=f.margin_bottom=0
    for i,line in enumerate(t.split('\n')):
        a=f.paragraphs[0] if i==0 else f.add_paragraph();a.text=line;a.font.name=font;a.font.size=Pt(size);a.font.color.rgb=rgb(color);a.font.bold=bold;a.space_after=Pt(8)
    return s
def shape(s,kind,x,y,w,h,color):
    z=s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h));z.fill.solid();z.fill.fore_color.rgb=rgb(color);z.line.fill.background();return z
def line(s,x,y,w,c='mint'):
    z=s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y), Inches(x+w), Inches(y));z.line.color.rgb=rgb(c);z.line.width=Pt(2);return z
def alt(sh,desc):
    for e in sh._element.iter():
        if e.tag.endswith('}cNvPr'): e.set('descr',desc);break
# Theme, shared master footer and custom title placeholder layout.
theme=p.slide_master.part.theme_part if hasattr(p.slide_master.part,'theme_part') else None
for rel in p.slide_master.part.rels.values():
    if rel.reltype.endswith('/theme'):
        from lxml import etree
        xml=etree.fromstring(rel.target_part.blob);ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        xml.find('.//a:majorFont/a:latin',ns).set('typeface','Georgia');xml.find('.//a:minorFont/a:latin',ns).set('typeface','Calibri')
        rel.target_part._blob=etree.tostring(xml)
master=p.slide_master
for s in list(master.shapes):
    if s.is_placeholder and s.placeholder_format.idx in [10,11,12]:s._element.getparent().remove(s._element)
text(master,'NBE Innovation Cycle 2026   /   Development prototype 2.2',.55,7.12,10,.2,12,'muted')
num=text(master,'',12.05,7.12,.65,.22,12,'muted');a=num.text_frame.paragraphs[0]._p
field=OxmlElement('a:fld');field.set('id','{A22A4FB1-477B-4EEC-A5CB-55BD2EF23F80}');field.set('type','slidenum');v=OxmlElement('a:t');v.text='1';field.append(v);a.append(field)
for k,z in enumerate(master.shapes,2):
    for e in z._element.iter():
        if e.tag.endswith('}cNvPr'): e.set('id',str(k))
layout=p.slide_layouts[5];layout.name='Conference / headline and evidence'
for s in list(layout.shapes):
    if s.is_placeholder and s.placeholder_format.idx!=0:s._element.getparent().remove(s._element)
title=layout.placeholders[0];title.left=Inches(.55);title.top=Inches(.43);title.width=Inches(12.15);title.height=Inches(1.2)
sources=[]
def slide(title,note,source):
    s=p.slides.add_slide(layout);s.background.fill.solid();s.background.fill.fore_color.rgb=rgb('bg')
    t=s.shapes.title;t.text=title;t.text_frame.word_wrap=True;t.text_frame.margin_left=0;t.text_frame.margin_top=0
    for a in t.text_frame.paragraphs:a.alignment=PP_ALIGN.LEFT;a.font.name='Georgia';a.font.size=Pt(34);a.font.bold=True;a.font.color.rgb=rgb('text')
    s.notes_slide.notes_text_frame.text=note
    text(s,source,.58,6.64,12.15,.38,12,'muted')
    sources.append((len(p.slides),title,source));return s
def caption(s,t):text(s,t,.58,5.96,12.1,.55,20,'amber')
def picture(s,path,x,y,w,h,desc):
    z=s.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h));alt(z,desc);return z
def chart(s,cats,series,x,y,w,h,kind=XL_CHART_TYPE.COLUMN_CLUSTERED):
    d=CategoryChartData();d.categories=cats
    for name,vals in series:d.add_series(name,vals)
    z=s.shapes.add_chart(kind,Inches(x),Inches(y),Inches(w),Inches(h),d);c=z.chart
    c.has_title=False;c.font.name='Calibri';c.font.size=Pt(18);c.font.color.rgb=rgb('text');c.has_legend=len(series)>1
    if c.has_legend:c.legend.position=XL_LEGEND_POSITION.BOTTOM;c.legend.include_in_layout=False
    for i,ser in enumerate(c.series):ser.format.fill.solid();ser.format.fill.fore_color.rgb=rgb(['mint','muted'][i%2]);ser.format.line.fill.background()
    c.plots[0].has_data_labels=True;c.plots[0].data_labels.font.size=Pt(18);c.plots[0].data_labels.font.color.rgb=rgb('text');c.plots[0].data_labels.position=XL_LABEL_POSITION.OUTSIDE_END
    if kind!=XL_CHART_TYPE.DOUGHNUT:
        c.value_axis.minimum_scale=0;c.value_axis.maximum_scale=100;c.value_axis.major_unit=25;c.value_axis.has_major_gridlines=True;c.value_axis.major_gridlines.format.line.color.rgb=rgb('panel');c.category_axis.tick_labels.font.color.rgb=rgb('text');c.value_axis.tick_labels.font.color.rgb=rgb('muted')
    alt(z,'Editable chart: '+str(cats)+'; '+str(series));return c

s=slide('Self-Healing\nLog Intelligence',
'We built this development prototype for the NBE Innovation Cycle 2026. We turn original operational logs into a view that helps an operator investigate unusual behavior. Today we will show what the system actually does, how we tested it and what still needs validation. We distinguish the working anomaly detectors from the experimental error forecasts throughout. Our goal is to make the next pilot decision understandable to both technical and business colleagues.',
'Pola Adolf and Youssef Atef / Release 2.2')
s.shapes.title.left=Inches(.58);s.shapes.title.width=Inches(12.1);s.shapes.title.top=Inches(1.45);s.shapes.title.height=Inches(2.1)
for a in s.shapes.title.text_frame.paragraphs:a.font.size=Pt(56)
text(s,'From logs to foresight',.58,3.95,10,.7,30,'mint',font='Georgia');text(s,'NBE Innovation Cycle 2026',.58,5.1,10,.5,22)

s=slide('Reactive support begins after business impact',
'We start with the challenge described in our kickoff workbook. Support reacts to incidents after the business has felt the impact. The diagram illustrates that sequence rather than a measured incident or a quantified delay. Logs already contain useful operational evidence, but reviewing large volumes manually makes that evidence difficult to interpret. We aim to give operators an earlier, clearer view of unusual behavior while keeping their judgment central to the response.',
'Source: Self_Healing.xlsx, Sheet1 B4; illustrative sequence, no measured timings')
line(s,1.1,3.35,10.9)
for i,(a,b) in enumerate([('Application fails','Operational signal'),('Business feels it','Service impact'),('Support responds','Manual investigation')]):
    x=.75+i*4.1;shape(s,MSO_SHAPE.OVAL,x,3.17,.34,.34,'amber' if i<2 else 'mint');text(s,a,x,2.3,3.6,.7,27);text(s,b,x,3.85,3.6,.7,22,'muted')

s=slide('Phase 1 sets four goals for a future pilot',
'We verified these four targets against the original kickoff workbook on the owner’s device. They are program goals, not measured improvements from this prototype. Mean time to recovery means how long service restoration takes. We would need a baseline, an agreed pilot scope and operational measurement before claiming any reduction. This project supplies the first technical building block. The percentage targets do not describe our model accuracy, and the pilot owners should confirm their use in the final business case.',
'Source: docs/business_case_targets.md; Self_Healing.xlsx B11:B15')
for i,(n,label,val) in enumerate([('Up to 40%','Lower recovery time',40),('50%','Fewer repeat incidents',50),('30%','Less manual effort',30),('Above 60%','Proactive detection',60)]):
    x=.55+i*3.2
    c=chart(s,['Target','Remaining'],[('Goal',[val,100-val])],x,2.15,2.65,2.65,XL_CHART_TYPE.DOUGHNUT);c.plots[0].has_data_labels=False;c.plots[0].hole_size=85
    c._chartSpace.find('.//{http://schemas.openxmlformats.org/drawingml/2006/chart}holeSize').set('val','85')
    for j,pt in enumerate(c.series[0].points):pt.format.fill.solid();pt.format.fill.fore_color.rgb=rgb('mint' if j==0 else 'panel')
    text(s,n,x+.1,4.55,2.8,.5,25,'mint');text(s,label,x,5,2.9,.8,22)
caption(s,'Kickoff targets. No business impact measured yet.')

s=slide('We parsed 754,369 supplied log records',
'We processed seven source families in the supplied archive. Apache access and Apache error are separate families because their measurements differ. The two application log families are also separate. This gives seven source families across five broad technology categories. Four sources had enough eligible history for a detector. The parsing report records twelve rejected records for audit. Parse success describes how successfully we read the files. It does not measure anomaly detection or prediction accuracy, and the archive is not proof of production representativeness.',
'Sources: outputs_v2/data_quality_report.md; DATASET_INVENTORY.md')
text(s,'754,369',.6,1.9,8,1.3,86,'mint',font='Georgia');text(s,'99.9984% parsed   /   12 retained for audit',.65,3.45,11,.6,26)
for i,label in enumerate(['Apache','IIS','Tomcat','Event Viewer','Application']):text(s,label,.65+i*2.5,4.9,2.4,.7,22,'muted')
caption(s,'7 source families examined; 4 detectors trained.')

s=slide('Five steps turn a raw file into an operator’s answer',
'We support two entry points. An operator can upload a supported original file through the dashboard, or an upstream system can send the defined feature-window JSON to the runtime. The parser applies the documented UTC policy and builds five-minute windows. Scoring needs twelve consecutive complete windows from the same source. A gap restarts that context. We then run the source-specific model and show measured evidence and checks. These checks guide investigation and do not execute remediation.',
'Sources: README.md architecture; MODEL_INTERFACE.md; raw_log_service.py')
text(s,'Original file',.7,1.95,4,.45,22,'mint');text(s,'Feature-window JSON joins at step 3',6.2,1.95,6.4,.45,20,'amber')
for i,(a,b) in enumerate([('1','Parse + UTC'),('2','5-minute windows'),('3','12-window history'),('4','Source models'),('5','Evidence + checks')]):
    x=.55+i*2.55;shape(s,MSO_SHAPE.ROUNDED_RECTANGLE,x,2.9,2.3,2,'panel');text(s,a,x+.15,3.12,1,.65,34,'mint');text(s,b,x+.15,4.05,2.05,.7,22)
    if i<4:shape(s,MSO_SHAPE.CHEVRON,x+2.33,3.6,.18,.3,'mint')
caption(s,'One hour of context. Missing coverage is not measured zero.')

s=slide('99.18 crosses the source’s review threshold',
'We ran the current release on the synthetic Apache demonstration file and recorded this result. The score is an anomaly percentile measured against training history. The learned review threshold is 98.99, so 99.18 triggers operator review. Isolation Forest separates observations using random partitions; unusual combinations tend to isolate more easily. Each source has its own detector. The current window contains 95 server-error responses among 300 requests, but the anomaly percentile is not that error rate or an outage probability.',
'Source: docs/demo_result.json; examples/apache_demo.log; synthetic current-release run')
text(s,'99.18',.6,1.95,6,1.35,88,'mint',font='Georgia');text(s,'Anomaly percentile',.65,3.45,6,.5,26)
text(s,'98.99',8.4,2.55,4,.8,48,'amber');text(s,'Review threshold',8.4,3.45,4,.5,24,'muted')
line(s,.65,4.55,11.9,'muted');shape(s,MSO_SHAPE.OVAL,11.65,4.4,.3,.3,'amber');shape(s,MSO_SHAPE.OVAL,12.1,4.4,.3,.3,'mint')
text(s,'0',.65,4.9,1,.4,18,'muted');text(s,'100',11.9,4.9,1,.4,18,'muted');caption(s,'Training-history rank. Not an outage probability.')

# Crop real screenshot into readable evidence panels, without changing values.
im=Image.open(r/'docs/images/dashboard.png')
for name,box in [('score',(660,337,1014,565)),('coverage',(347,971,637,1195)),('checks',(1125,989,1575,1424))]:im.crop(box).save(r/f'docs/images/{name}.png',optimize=True)
s=slide('The live dashboard makes its evidence visible',
'We captured these panels from a fresh browser run of release 2.2, using only the repository’s synthetic Apache log. The first panel shows the completed history and parsing coverage. The second shows the anomaly percentile and threshold. The third presents suggested checks. During the live demonstration we upload the same file and let the real model process it. This is a reproducible workflow demonstration, not independent validation on unseen customer incidents. We can export the assessment for inspection afterwards.',
'Source: fresh 1920 × 1080 browser session; docs/images/dashboard.png; synthetic input')
for name,x,w,h,title in [('coverage',.6,3.1,2.4,'1  Coverage'),('score',4.05,4.15,2.68,'2  Percentile'),('checks',8.55,4.15,4,'3  Checks')]:
    text(s,title,x,1.75,w,.55,24,'mint');picture(s,r/f'docs/images/{name}.png',x,2.45,w,h,'Actual release 2.2 '+name+' panel from synthetic upload')

s=slide('Four detectors follow the same release rules',
'We train a separate detector for each supported source because the features and expected volumes differ. This table gives eligible training windows and review flags on the same archived holdout windows. A flag count indicates how many windows need review. Without reviewed anomaly labels, it does not tell us how many were correct. Only Apache access receives an experimental forecast preview. We withhold the other previews because the available evidence is too weak or the forecast underperforms a simple baseline.',
'Sources: MODEL_RELEASE_2_2.md; outputs_v2/detector_v22_audit.json')
tab=s.shapes.add_table(5,4, Inches(.6), Inches(2), Inches(12.1), Inches(3.6)).table
data=[['Source','Training windows','Flags / holdout','Forecast'],['Apache access','3,548','30 / 1,176','Experimental'],['Apache error','3,541','11 / 1,174','Withheld'],['IIS W3C','354','0 / 104','Withheld'],['Event Viewer','3,551','122 / 1,188','Withheld']]
for i,row in enumerate(data):
    for j,v in enumerate(row):
        cell=tab.cell(i,j);cell.text=v;cell.fill.solid();cell.fill.fore_color.rgb=rgb('panel' if i%2==0 else 'bg')
        for a in cell.text_frame.paragraphs:a.font.name='Calibri';a.font.size=Pt(20);a.font.color.rgb=rgb('mint' if i==0 else ('amber' if j==3 else 'text'))
caption(s,'Review flags measure workload, not validated anomaly accuracy.')

s=slide('Apache ranks future errors above a simple baseline',
'We compare average precision, a measure of how well a model ranks windows containing future recorded errors. Persistence is a simple rule that assumes the current error state continues. Apache’s archive results rank better at both horizons. However, validation had zero positive windows, so we could not validate the threshold. The archive test has also been examined previously. We therefore show an experimental preview, not a validated incident probability or production accuracy. Future labels must distinguish a new incident from errors that continue.',
'Source: MODEL_EVALUATION.md; archive test already inspected; AP means average precision')
chart(s,['5 minutes','15 minutes'],[('Model AP',[96.33,90.70]),('Persistence AP',[91.46,87.07])],.7,1.8,7.6,4.45)
text(s,'Persistence assumes the current error state continues.',8.8,2.3,3.8,1.7,25)
text(s,'Experimental',8.8,4.35,3.8,.5,27,'amber');text(s,'Validation had zero positive windows.',8.8,5,3.8,1.05,23,'amber')

s=slide('A harder test exposed too many false alerts',
'We also checked a later Windows workstation dataset rather than relying only on the original archive. On the fifteen-minute System forecast, the saved threshold caught 41 of 87 windows containing future errors and produced 262 false alerts. That yields approximately 13.5 percent precision: only a small share of raised alerts matched the target. These are recorded-error windows, not confirmed incidents. We withheld that forecast from operators. Testing and withholding a weak result is part of our release discipline.',
'Source: MODEL_RELEASE_2_2.md; 13.5% = 41 / (41 + 262), rounded')
for x,n,l,c in [(.6,'41 / 87','Positive windows caught','mint'),(4.85,'262','False-alert windows','red'),(9.05,'13.5%','Alert precision','amber')]:
    text(s,n,x,2.4,4,1.3,61,c,font='Georgia');text(s,l,x,4.05,3.7,1,24)
caption(s,'Windows System, 15-minute forecast: withheld from operators.')

s=slide('Today’s capabilities have clear boundaries',
'We can demonstrate original-file ingestion, the documented UTC policy, anomaly scoring, measured evidence and operational checks. Eighteen automated tests passed during preparation. Those tests check software behavior and leakage safeguards; they are not a model accuracy estimate. We have not validated confirmed incident prediction, production accuracy or root-cause identification. The system does not execute automatic remediation. Keeping these boundaries visible helps a pilot owner understand what they can evaluate today and what needs additional evidence before operational reliance.',
'Sources: STATUS.md; TESTING.md; MODEL_RELEASE_2_2.md')
text(s,'Working prototype',.65,1.95,5.8,.6,29,'mint');text(s,'Not established',7,1.95,5.7,.6,29,'amber')
text(s,'Original-file ingestion\nUTC policy\nAnomaly evidence\n18 software tests',.65,2.95,5.7,2.7,27)
text(s,'Incident prediction\nProduction accuracy\nRoot cause\nAutomatic remediation',7,2.95,5.7,2.7,27)

s=slide('A monitored pilot needs operational evidence',
'We propose a limited, monitored pilot rather than a production rollout. First we need confirmed time zones and system relationships, plus reviewed incident labels. We then reserve an untouched later period and train targets for incident onset. We agree an alert budget with IT and assess performance using recall, precision, lead time and false alerts. Reversible remediation would be a separate later approval. Our immediate ask is a defined pilot scope, owner confirmation of the data assumptions and incident labels that support reliable validation.',
'Sources: PROJECT_ROADMAP.md; INCIDENT_PREDICTION_PLAN.md; schemas/incident_label.schema.json')
for i,label in enumerate(['Confirm clocks\nand topology','Review incident\nlabels','Reserve later\ndata','Train for\nonset','Agree alert\nbudget','Approve safe\nremediation']):
    x=.6+i*2.1;line(s,x,3.25,1.85,'muted');shape(s,MSO_SHAPE.OVAL,x,3.12,.26,.26,'mint');text(s,str(i+1),x,2.3,1,.5,30,'mint');text(s,label,x,3.7,1.95,1.2,20)
caption(s,'The ask: confirmed data assumptions, incident labels and a pilot scope.')

s=slide('Thank you',
'We welcome questions about the current demonstration and the next validation stage. The public repository contains the model interface, evaluation evidence and reproducible synthetic sample. The QR code opens that repository. Public availability does not grant an open-source license; the owners have retained all rights at this stage. We are asking for a scoped pilot and the operational evidence needed to evaluate incident onset responsibly. We can show the upload flow again or explain any score and its limitations.',
'Pola Adolf and Youssef Atef / NBE Innovation Cycle 2026')
qr=qrcode.make('https://github.com/PolaAdolf/self-healing-log-intelligence');qr.save(r/'docs/images/repository-qr.png');picture(s,r/'docs/images/repository-qr.png',9,2.05,3.2,3.2,'QR code linking to the public project repository')
text(s,'Let’s define the monitored pilot.',.6,2.4,8,1.6,43,'mint',font='Georgia');text(s,'github.com/PolaAdolf/\nself-healing-log-intelligence',.65,4.8,8,1.05,25)

s=slide('Chronological evaluation protects the time boundary',
'We divide each source timeline chronologically into training, validation and test portions. Features use only observations available at the scoring window. Forecast targets look forward, so rows whose targets cross a split boundary must be excluded. This is the purge illustrated below. Our archive test has already been inspected, so it cannot serve as an untouched final validation set. A production claim requires a genuinely later period with representative normal operation and reviewed incidents, plus the same availability rules used in deployment.',
'Appendix A1 / Sources: failure_prediction.py; DATA_TIME_AND_FAILURE_POLICY.md')
for x,w,t,c in [(.6,7.2,'60% training','mint'),(7.8,2.4,'20% validation','amber'),(10.2,2.4,'20% test','muted')]:
    shape(s,MSO_SHAPE.RECTANGLE,x,2.7,w,1.2,c);text(s,t,x+.1,3.05,w-.2,.5,22,'bg',bold=True)
text(s,'Exclude targets crossing each boundary',.65,4.35,11,.7,27,'amber');text(s,'Features use past observations only.',.65,5.4,11,.55,25)

s=slide('UTC conversion and UTC assumptions stay separate',
'We normalize the model timeline to UTC while preserving what the source actually tells us. Apache and Tomcat access records include offsets, which we convert. IIS uses the W3C timestamp convention. Apache error, Event Viewer exports and application log prefixes lack offsets in the supplied files, so the selected project policy assumes UTC and records that assumption. We still need source-owner confirmation. If the assumption changes, rebuilding the source data and retraining is necessary; relabelling a runtime timestamp alone would be incorrect.',
'Appendix A2 / Source: DATA_TIME_AND_FAILURE_POLICY.md')
tab=s.shapes.add_table(4,2, Inches(.6), Inches(2.05), Inches(12), Inches(3.65)).table
for i,row in enumerate([['Source','Time policy'],['Apache + Tomcat access','Convert embedded offset'],['IIS W3C','UTC by format'],['Error + Event Viewer + app logs','Assume UTC; owner confirmation needed']]):
    for j,v in enumerate(row):
        cell=tab.cell(i,j);cell.text=v;cell.fill.solid();cell.fill.fore_color.rgb=rgb('panel' if i%2==0 else 'bg')
        for a in cell.text_frame.paragraphs:a.font.name='Calibri';a.font.size=Pt(22);a.font.color.rgb=rgb('mint' if i==0 else 'text')

s=slide('Missing evidence limits what we can conclude',
'We keep four validity risks explicit. Recorded errors are not the same as reviewed incidents. Rare positives can make ordinary accuracy misleading because an always-normal rule can appear strong. Some timestamps rely on the selected UTC assumption. Finally, the archive lacks collector heartbeat and ingestion timestamps, so source coverage is inferred rather than independently verified. We cannot treat missing logs as proof of downtime or infer causality from simultaneous events. The pilot must address these gaps before we claim reliable incident prediction.',
'Appendix A3 / Sources: STATUS.md; DATA_TIME_AND_FAILURE_POLICY.md; INCIDENT_PREDICTION_PLAN.md')
for i,(a,b) in enumerate([('Target mismatch','Errors are not confirmed incidents.'),('Class imbalance','High accuracy can hide missed failures.'),('Time assumptions','Some sources still need UTC confirmation.'),('Missing telemetry','No heartbeat or ingestion timestamps.')]):
    y=1.95+i*1.1;text(s,a,.65,y,3.4,.7,25,'amber');text(s,b,4.25,y,8.2,.7,25)

# Metadata and structural checks before export.
p.core_properties.title='Self-Healing Log Intelligence / NBE Innovation Cycle 2026'
p.core_properties.author='Pola Adolf and Youssef Atef';p.core_properties.subject='Release 2.2 conference deck with evidence and limits'
for i,s in enumerate(p.slides):
    n=len(s.notes_slide.notes_text_frame.text.split());assert 60<=n<=110,(i+1,n)
    for z in s.shapes:assert z.left>=0 and z.top>=0 and z.left+z.width<=p.slide_width+100 and z.top+z.height<=p.slide_height+100,(i+1,z.name)
dest=out/'NBE_Innovation_Cycle_2026_Conference_Deck.pptx';p.save(dest)
(r/'docs/DECK_SOURCES.md').write_text('# Conference slide sources\n\nAll numbered results are descriptive archive results or a clearly marked synthetic run. Business values are unmeasured goals.\n\n| Slide | Headline | Evidence |\n| --- | --- | --- |\n'+''.join(f'| {i} | {t.replace(chr(10)," ")} | {src} |\n' for i,t,src in sources)+'\nTheme fallback fonts: Georgia headings and Calibri body. All main charts, tables and process diagrams remain editable. The original final deck is preserved byte-for-byte.\n',encoding='utf-8')
print(dest)





