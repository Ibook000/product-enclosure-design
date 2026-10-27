"""Portable enclosure CLI; generated models are examples, not manufacturing certification."""
import argparse,hashlib,json,math,os,shutil,subprocess,sys,zipfile
from pathlib import Path
from stl_check import inspect

HERE=Path(__file__).resolve().parent
FLAGS={'creationflags':0x08000000} if os.name=='nt' else {}
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.partial')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)
def load(path):
    path=Path(path).resolve();cfg=json.loads(path.read_text(encoding='utf-8'))
    if cfg.get('units')!='mm':raise ValueError('Builder requires explicit mm; convert source data deliberately')
    s=cfg['shell'];lid=cfg['lid'];w,d,h=s['outer_size'];wall=s['wall'];floor=s['floor']
    values=[w,d,h,wall,floor,lid['plate_thickness'],lid['lip_depth'],lid['lip_wall']]
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in values):raise ValueError('Dimensions must be positive finite mm values')
    for key in ['clearance_per_side','seam_gap']:
        if not math.isfinite(lid[key]) or lid[key]<0:raise ValueError(key+' must be nonnegative')
    if w<=2*wall or d<=2*wall or h<=floor:raise ValueError('Wall/floor consumes the cavity')
    if not 0<=s['corner_radius']<=min(w,d)/2:raise ValueError('Invalid corner radius')
    if min(w,d)-2*wall-2*lid['clearance_per_side']-2*lid['lip_wall']<=0:raise ValueError('Lid lip has no interior')
    if lid['lip_depth']>=h-floor or lid['lip_depth']<=lid['seam_gap']:raise ValueError('Lip depth must engage cavity and remain above the floor')
    vertices=s.get('profile_vertices',128)
    if not isinstance(vertices,int) or vertices<16 or vertices%4:raise ValueError('profile_vertices must be an integer multiple of 4, at least 16')
    for opening in cfg.get('openings',[]):
        if opening.get('part') not in ['base','lid'] or opening.get('axis') not in ['x','y','z'] or opening.get('shape') not in ['rect','circle']:
            raise ValueError('Opening requires part base/lid, axis x/y/z and shape rect/circle')
        coordinates=opening.get('center',[])
        if len(coordinates)!=3 or not all(math.isfinite(v) for v in coordinates):raise ValueError('Opening center must contain three finite mm coordinates')
        dimensions=[opening.get('depth',0)]+(opening.get('size',[]) if opening['shape']=='rect' else [opening.get('diameter',0)])
        if len(dimensions)!=(3 if opening['shape']=='rect' else 2) or not all(math.isfinite(v) and v>0 for v in dimensions):raise ValueError('Opening dimensions must be positive')
    for boss in cfg.get('bosses',[]):
        if len(boss.get('xy',[]))!=2 or not all(math.isfinite(v) for v in boss['xy']):raise ValueError('Boss requires finite xy coordinates')
        if not all(math.isfinite(boss[k]) and boss[k]>0 for k in ['hole_diameter','outer_diameter','height']):raise ValueError('Boss dimensions must be positive finite mm values')
        if not 0<boss['hole_diameter']<boss['outer_diameter'] or boss['height']<=0:raise ValueError('Invalid boss dimensions')
        if boss['height']>=h-floor:raise ValueError('Boss extends beyond cavity')
    ref=cfg.get('reference')
    if ref:
        if len(ref.get('center',[]))!=3 or len(ref.get('size',[]))!=3:raise ValueError('Reference needs center and size vectors')
        if not all(math.isfinite(v) for v in ref['center']+ref['size']) or not all(v>0 for v in ref['size']):raise ValueError('Invalid reference envelope')
        x,y,z=ref['center'];a,b,c=ref['size']
        if abs(x)+a/2>w/2-wall or abs(y)+b/2>d/2-wall or z-c/2<floor or z+c/2>h:
            raise ValueError('Reference AABB does not fit nominal straight cavity bounds')
    tolerance=cfg.get('verification',{}).get('dimension_tolerance_mm',.001)
    if not math.isfinite(tolerance) or tolerance<=0:raise ValueError('Dimension comparison tolerance must be positive and finite')
    signature={k:v for k,v in cfg.items() if k not in ['tools','output_dir']}
    signature['builder_sha256']=hashlib.sha256((HERE/'blender_enclosure.py').read_bytes()).hexdigest()
    token=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()[:16]
    cfg['_project']=str(path);cfg['_output']=str((path.parent/cfg.get('output_dir','output')/('design-'+token)).resolve())
    cfg['_signature']=token
    return cfg

def blender(cfg,override=None):
    value=override or cfg.get('tools',{}).get('blender') or os.environ.get('BLENDER_BIN') or 'blender'
    if ('/' in value or '\\' in value) and not Path(value).is_absolute():value=str((Path(cfg['_project']).parent/value).resolve())
    found=shutil.which(value)
    if not found and Path(value).is_file():found=str(Path(value).resolve())
    if not found:raise ValueError('Blender not found: set --blender, tools.blender, BLENDER_BIN or PATH')
    return found

def verify(cfg):
    out=Path(cfg['_output']);reports=[]
    for name in ['base','lid']:
        result=inspect(out/(name+'.stl'),'mm');reports.append(result)
        if not result['exact_coordinate_topology_checks_passed'] or result['connected_components']!=1:
            write(out/'mesh-verification.json',dict(passed=False,parts=reports));raise ValueError('Exported '+name+' failed topology/winding/volume checks')
    w,d,h=cfg['shell']['outer_size'];expected={'base':[w,d,h],'lid':[w,d,cfg['lid']['plate_thickness']+cfg['lid']['lip_depth']]}
    tolerance=cfg.get('verification',{}).get('dimension_tolerance_mm',.001)
    for report in reports:
        role=Path(report['file']).stem
        if any(abs(a-b)>tolerance for a,b in zip(report['dimensions'],expected[role])):raise ValueError('Re-read STL dimensions differ from configured outer dimensions: '+role)
    result=dict(automatic_checks_passed=True,signature=cfg['_signature'],parts=reports,
      checked=['finite coordinates','exact edge adjacency','edge winding','connected components','nonzero triangle area','float32 degeneracy','positive signed volume','STL dimension readback'],
      not_established=['self intersections','vertex-manifoldness','global wall thickness','full assembly collision','manufacturing fit','printability','strength'],
      note='Nominal reference-envelope bounds do not replace actual connector, corner, motion or assembly clearance checks.')
    write(out/'mesh-verification.json',result);print(json.dumps(result,ensure_ascii=False,indent=2));return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['init','check','build','verify','mesh-check','package']);p.add_argument('project')
    p.add_argument('--blender');p.add_argument('--units');p.add_argument('--report');a=p.parse_args()
    if a.command=='init':
        target=Path(a.project)
        if target.exists():raise ValueError('Refusing to overwrite existing project')
        write(target,json.loads((HERE.parent/'assets'/'enclosure-project.json').read_text(encoding='utf-8')));print('CREATED '+str(target.resolve()));return
    if a.command=='mesh-check':
        if not a.units:raise ValueError('STL has no inherent units: provide --units')
        result=inspect(a.project,a.units)
        if a.report:write(a.report,result)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    cfg=load(a.project);out=Path(cfg['_output'])
    if a.command=='check':print(json.dumps(dict(config_valid=True,output=str(out),
        warning='Example dimensions are not a real product measurement; nominal checks are not manufacturing approval.'),ensure_ascii=False,indent=2));return
    if a.command=='build':
        exe=blender(cfg,a.blender);out.mkdir(parents=True,exist_ok=True);write(out/'resolved.json',cfg)
        with (out/'blender.log').open('w',encoding='utf-8') as log:
            proc=subprocess.run([exe,'-b','--disable-autoexec','--python',str(HERE/'blender_enclosure.py'),'--','--config',str(out/'resolved.json')],
                stdout=log,stderr=log,timeout=cfg.get('tools',{}).get('timeout_seconds',1800),**FLAGS)
        if proc.returncode:raise RuntimeError((out/'blender.log').read_text(encoding='utf-8',errors='replace')[-3500:])
        verify(cfg);print('BUILT '+str(out));return
    if a.command=='verify':verify(cfg);return
    result=verify(cfg);manifest=['enclosure.blend','base.stl','lid.stl','build-report.json','mesh-verification.json']
    if cfg.get('preview',True):manifest+=['assembly-preview.png','exploded-preview.png']
    for name in manifest:
        if not (out/name).is_file():raise ValueError('Missing package file: '+name)
    portable={k:v for k,v in cfg.items() if not k.startswith('_')};portable.pop('tools',None);write(out/'project.json',portable);manifest+=['project.json']
    hashes={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in manifest};write(out/'SHA256.json',hashes);manifest+=['SHA256.json']
    bundle=out/'enclosure-delivery.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for name in manifest:z.write(out/name,name)
    print('PACKAGE '+str(bundle))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,FileNotFoundError,OverflowError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);raise SystemExit(1)
