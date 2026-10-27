"""Read-only STL diagnostics. No silent welding, repair, or print certification."""
import argparse, collections, json, math, re, struct
from pathlib import Path

def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def length(v):return math.sqrt(dot(v,v))

def read_stl(path):
    raw=Path(path).read_bytes();binary=False
    if len(raw)>=84:
        count=struct.unpack_from('<I',raw,80)[0];binary=(84+50*count==len(raw))
    triangles=[];normals=[]
    if binary:
        for i in range(count):
            values=struct.unpack_from('<12fH',raw,84+i*50)
            normals.append(tuple(values[:3]));triangles.append(tuple(tuple(values[j:j+3]) for j in [3,6,9]))
    else:
        text=raw.decode('ascii');vertices=[]
        for match in re.finditer(r'\bvertex\s+(\S+)\s+(\S+)\s+(\S+)',text,re.I):vertices.append(tuple(float(v) for v in match.groups()))
        for match in re.finditer(r'\bfacet\s+normal\s+(\S+)\s+(\S+)\s+(\S+)',text,re.I):normals.append(tuple(float(v) for v in match.groups()))
        if not vertices or len(vertices)%3:raise ValueError('Invalid ASCII STL vertex count')
        triangles=[tuple(vertices[i:i+3]) for i in range(0,len(vertices),3)]
    if not triangles:raise ValueError('STL contains no triangles')
    if any(not math.isfinite(v) for tri in triangles for p in tri for v in p):raise ValueError('STL contains non-finite coordinates')
    if any(not math.isfinite(v) for n in normals for v in n):raise ValueError('STL contains non-finite normals')
    return triangles,normals,'binary-float32' if binary else 'ascii-parsed-float64'

def inspect(path,units='mm'):
    if units not in ['mm','cm','m','inch']:raise ValueError('Specify units: mm/cm/m/inch; STL cannot establish them')
    tris,normals,kind=read_stl(path);points=[p for tri in tris for p in tri]
    low=[min(p[j] for p in points) for j in range(3)];high=[max(p[j] for p in points) for j in range(3)]
    center=[(a+b)/2 for a,b in zip(low,high)];edges=collections.defaultdict(list)
    parents=list(range(len(tris)))
    def find(x):
        while parents[x]!=x:parents[x]=parents[parents[x]];x=parents[x]
        return x
    degenerate=0;normal_mismatch=0;zero_normals=0;min_edge=float('inf');min_altitude=float('inf');worst_aspect=0;vol=0;f32_degenerate=0;f32_overflow=0
    for face,tri in enumerate(tris):
        a,b,c=tri;normal=cross(sub(b,a),sub(c,a));twice_area=length(normal)
        sides=[length(sub(a,b)),length(sub(b,c)),length(sub(c,a))]
        largest=max(sides);smallest=min(sides)
        min_edge=min(min_edge,smallest)
        altitude=twice_area/largest if largest else 0;min_altitude=min(min_altitude,altitude)
        worst_aspect=max(worst_aspect,largest/altitude if altitude else 0)
        if twice_area==0:degenerate+=1
        aa,bb,cc=[sub(p,center) for p in tri];vol+=dot(aa,cross(bb,cc))/6
        if face<len(normals):
            stored=normals[face];size=length(stored)
            if size==0:zero_normals+=1
            elif twice_area and dot(stored,normal)/(size*twice_area)<.999:normal_mismatch+=1
        try:
            quantized=[struct.unpack('<3f',struct.pack('<3f',*p)) for p in tri]
            if length(cross(sub(quantized[1],quantized[0]),sub(quantized[2],quantized[0])))==0:f32_degenerate+=1
        except OverflowError:f32_overflow+=1
        for p,q in [(a,b),(b,c),(c,a)]:
            key=tuple(sorted((p,q)));edges[key].append((face,p==key[0]))
    boundary=sum(len(v)==1 for v in edges.values());nonmanifold=sum(len(v)>2 for v in edges.values());winding=0
    for uses in edges.values():
        if len(uses)>1:
            for face,_ in uses[1:]:parents[find(face)]=find(uses[0][0])
        if len(uses)==2 and uses[0][1]==uses[1][1]:winding+=1
    components=len({find(i) for i in range(len(tris))})
    max_coordinate=max(abs(v) for p in points for v in p)
    ulp=(2**(math.floor(math.log2(max_coordinate))-23)) if max_coordinate else 2**-149
    if not all(math.isfinite(v) for v in [vol,worst_aspect]):raise ValueError('Derived geometry exceeds floating-point numeric range')
    passed=not (boundary or nonmanifold or winding or degenerate or normal_mismatch or f32_degenerate or f32_overflow) and vol>0
    return dict(file=str(Path(path).resolve()),declared_units=units,encoding=kind,triangles=len(tris),
      bounds_min=low,bounds_max=high,dimensions=[b-a for a,b in zip(low,high)],connected_components=components,
      boundary_edges=boundary,edges_with_more_than_two_faces=nonmanifold,inconsistent_winding_edges=winding,
      zero_area_triangles=degenerate,serialized_normal_mismatches=normal_mismatch,zero_serialized_normals=zero_normals,
      signed_volume=vol,minimum_edge=minimum_finite(min_edge),minimum_altitude=minimum_finite(min_altitude),maximum_aspect_ratio=worst_aspect,
      float32_degenerate_triangles=f32_degenerate,float32_ulp_near_max_coordinate=ulp,
      float32_overflow_triangles=f32_overflow,
      exact_coordinate_topology_checks_passed=passed,
      not_established=['vertex-manifoldness','absence of self intersections','global minimum wall thickness','physical fit','printability','strength'])

def minimum_finite(value):return value if math.isfinite(value) else None

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('file');p.add_argument('--units',required=True);p.add_argument('--report')
    a=p.parse_args()
    try:
        result=inspect(a.file,a.units);text=json.dumps(result,ensure_ascii=False,indent=2)
        if a.report:Path(a.report).write_text(text,encoding='utf-8')
        print(text)
    except (ValueError,OverflowError) as exc:p.exit(1,'ERROR: '+str(exc)+'\n')
