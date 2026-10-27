"""Parametric two-part rigid housing example. Coordinates and exports are mm."""
import argparse,json,math,os,struct,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Vector

def contour(width,depth,radius,n):
    radius=max(0,min(radius,min(width,depth)/2))
    result=[]
    for i in range(n):
        angle=2*math.pi*i/n;dx,dy=math.cos(angle),math.sin(angle)
        low=0;high=math.hypot(width/2,depth/2)*1.01
        for _ in range(48):
            t=(low+high)/2;x=abs(dx*t)-(width/2-radius);y=abs(dy*t)-(depth/2-radius)
            distance=min(max(x,y),0)+math.hypot(max(x,0),max(y,0))-radius
            if distance<=0:low=t
            else:high=t
        x,y=dx*low,dy*low
        result.append((0 if abs(x)<1e-10 else x,0 if abs(y)<1e-10 else y))
    return result

def profile(name,rings,n,close_first=True,close_last=True):
    vertices=[]
    for width,depth,radius,z in rings:vertices.extend((x,y,z) for x,y in contour(width,depth,radius,n))
    faces=[]
    for j in range(len(rings)-1):
        for i in range(n):faces.append((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i))
    if close_first:faces.append(tuple(reversed(range(n))))
    if close_last:faces.append(tuple((len(rings)-1)*n+i for i in range(n)))
    mesh=bpy.data.meshes.new(name+'Mesh');mesh.from_pydata(vertices,[],faces);mesh.update()
    ob=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(ob);recalc(ob);return ob

def recalc(ob):
    bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    if bm.calc_volume()<0:bmesh.ops.reverse_faces(bm,faces=list(bm.faces))
    bm.to_mesh(ob.data);bm.free();ob.data.update()

def volume(ob):
    bm=bmesh.new();bm.from_mesh(ob.data);value=abs(bm.calc_volume());bm.free();return value

def boolean(ob,cutter,operation):
    before=volume(ob);bpy.context.view_layer.objects.active=ob
    mod=ob.modifiers.new('Enclosure '+operation,'BOOLEAN');mod.operation=operation;mod.solver='EXACT';mod.object=cutter
    bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(cutter,do_unlink=True);recalc(ob)
    after=volume(ob)
    if operation=='DIFFERENCE' and not after<before-1e-7:raise ValueError('Opening did not intersect '+ob.name)
    if operation=='UNION' and not after>before+1e-7:raise ValueError('Boss did not add volume to '+ob.name)

def cylinder(name,center,radius,depth,axis='z'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=radius,depth=depth,location=center)
    ob=bpy.context.object;ob.name=name
    if axis=='x':ob.rotation_euler.y=math.pi/2
    if axis=='y':ob.rotation_euler.x=math.pi/2
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);return ob

def material(name,color):
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    p=mat.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=.35
    return mat

def export_part(ob,path):
    mesh=ob.data;mesh.calc_loop_triangles();world=ob.matrix_world
    vertices=[world@v.co for v in mesh.vertices];minimum=min(v.z for v in vertices)
    triangles=[]
    for tri in mesh.loop_triangles:
        p=[Vector((vertices[j].x,vertices[j].y,vertices[j].z-minimum)) for j in tri.vertices]
        normal=(p[1]-p[0]).cross(p[2]-p[0]);normal.normalize()
        triangles.append((normal,p))
    temp=path.with_suffix('.partial.stl')
    with temp.open('wb') as f:
        f.write(b'Enclosure export; coordinates in mm; print-bed Z shift recorded'.ljust(80,b' '));f.write(struct.pack('<I',len(triangles)))
        for normal,tri in triangles:f.write(struct.pack('<12fH',*normal,*(v for p in tri for v in p),0))
    os.replace(temp,path)
    return dict(file=path.name,triangles=len(triangles),assembly_to_print_translation_mm=[0,0,-minimum])

def preview(sc,parts,output,w,d,h):
    for ob in parts:ob.data.materials.append(material(ob.name+'Material',(.22,.26,.24) if ob.name=='Base' else (.68,.72,.65)))
    world=bpy.data.worlds.new('EnclosureWorld');world.use_nodes=True;sc.world=world
    world.node_tree.nodes['Background'].inputs['Color'].default_value=(.04,.05,.045,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.45
    span=max(w,d,h)
    for offset,power,size in [((-1,-1.6,2.5),150,2),((1.5,1,1.8),110,1.5)]:
        data=bpy.data.lights.new('Softbox','AREA');data.energy=power*span**2;data.shape='DISK';data.size=span*size
        ob=bpy.data.objects.new(data.name,data);sc.collection.objects.link(ob);ob.location=Vector(offset)*span
        ob.rotation_euler=(Vector((0,0,h/2))-ob.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('EnclosureCamera');cam=bpy.data.objects.new(data.name,data);sc.collection.objects.link(cam);sc.camera=cam
    data.type='ORTHO';data.ortho_scale=span*1.75;data.clip_start=.01;data.clip_end=span*100
    cam.location=(span*1.2,-span*1.4,span*1.5);target=Vector((0,0,h*.55));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    sc.render.engine='BLENDER_EEVEE_NEXT';sc.eevee.taa_render_samples=16;sc.render.resolution_x=1000;sc.render.resolution_y=700;sc.render.resolution_percentage=100
    sc.render.image_settings.file_format='PNG';sc.render.filepath=str(output/'assembly-preview.png');bpy.ops.render.render(write_still=True)
    lid=parts[1];original=lid.location.copy();lid.location.z+=h*.65
    sc.render.filepath=str(output/'exploded-preview.png');bpy.ops.render.render(write_still=True);lid.location=original

def main():
    args=sys.argv[sys.argv.index('--')+1:];parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    a=parser.parse_args(args);cfg=json.loads(Path(a.config).read_text(encoding='utf-8'));out=Path(cfg['_output']);out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True);sc=bpy.context.scene;sc.unit_settings.system='METRIC';sc.unit_settings.scale_length=.001
    p=cfg['shell'];w,d,h=p['outer_size'];wall=p['wall'];floor=p['floor'];r=p['corner_radius'];n=p.get('profile_vertices',128)
    lidcfg=cfg['lid'];t=lidcfg['plate_thickness'];gap=lidcfg['seam_gap'];fit=lidcfg['clearance_per_side'];lip=lidcfg['lip_depth'];lw=lidcfg['lip_wall']
    base=profile('Base',[(w,d,r,0),(w,d,r,h),(w-2*wall,d-2*wall,max(0,r-wall),h),(w-2*wall,d-2*wall,max(0,r-wall),floor)],n)
    ow,od=w-2*wall-2*fit,d-2*wall-2*fit;orr=max(0,r-wall-fit)
    # A single connected profile: top plate, underside ledge, outer/inner lip.
    lid=profile('Lid',[(w,d,r,t),(w,d,r,0),(ow,od,orr,0),(ow,od,orr,-lip),
                       (ow-2*lw,od-2*lw,max(0,orr-lw),-lip),(ow-2*lw,od-2*lw,max(0,orr-lw),0)],n)
    lid.location.z=h+gap;bpy.context.view_layer.update()
    for index,boss in enumerate(cfg.get('bosses',[])):
        x,y=boss['xy'];height=boss['height'];overlap=min(.1,floor/4)
        outer=cylinder('Boss'+str(index),(x,y,floor+(height-overlap)/2),boss['outer_diameter']/2,height+overlap)
        boolean(base,outer,'UNION')
        bore=cylinder('Bore'+str(index),(x,y,floor+height/2+.025),boss['hole_diameter']/2,height+.10)
        boolean(base,bore,'DIFFERENCE')
    for index,opening in enumerate(cfg.get('openings',[])):
        target=base if opening['part']=='base' else lid;axis=opening['axis'];center=opening['center'];depth=opening['depth']
        if opening['shape']=='circle':cut=cylinder('Opening'+str(index),center,opening['diameter']/2,depth,axis)
        else:
            a,b=opening['size'];dims={'x':(depth,a,b),'y':(a,depth,b),'z':(a,b,depth)}[axis]
            bpy.ops.mesh.primitive_cube_add(size=1,location=center);cut=bpy.context.object;cut.dimensions=dims
            bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        boolean(target,cut,'DIFFERENCE')
    if cfg.get('reference'):
        ref=cfg['reference'];bpy.ops.mesh.primitive_cube_add(size=1,location=ref['center']);ob=bpy.context.object;ob.name='ReferenceEnvelope'
        ob.dimensions=ref['size'];bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);ob.data.materials.append(material('Reference',(.03,.23,.10)))
    exports=[export_part(ob,out/(ob.name.lower()+'.stl')) for ob in [base,lid]]
    report=dict(units='mm',exports=exports,nominal_lip_clearance_per_side_mm=fit,
        nominal_cavity_size_mm=[w-2*wall,d-2*wall,h-floor],
        model_note='Parametric rigid housing example. Alignment lip is not a latch or fastening system.',
        unverified=['actual manufacturing fit','global minimum wall thickness','strength','fastener engagement','self intersections'])
    if cfg.get('preview',True):preview(sc,[base,lid],out,w,d,h)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'enclosure.blend'))
    (out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ENCLOSURE_BUILD_COMPLETE '+str(out),flush=True)

if __name__=='__main__':main()
