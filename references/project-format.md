# 参数与工具

基础生成器提供圆角矩形上下壳起点，不读取真实 PCB 或器件。所有值为 mm，路径相对 JSON；复杂产品用任务适配器。

| 参数 | 含义 |
|---|---|
| units / datums | 生成器要求 mm；本例底面中心为原点，X 宽、Y 深、Z 向上 |
| shell.outer_size | 宽、深、基壳高 |
| shell.wall / floor | 名义直壁厚、底厚；不是全局壁厚扫描 |
| shell.corner_radius / profile_vertices | 平面圆角及径向多边形采样数，须为 4 的倍数且至少 16 |
| lid.plate_thickness | 盖板厚 |
| lid.clearance_per_side | 止口对基壳内腔的单侧名义间隙 |
| lid.seam_gap | 盖板下表面与基壳上沿的竖向缝隙 |
| lid.lip_depth / lip_wall | 下伸定位止口的深度/壁厚，不是卡扣 |
| bosses | xy、outer_diameter、hole_diameter、height；孔不自动构成螺纹 |
| openings | part:base/lid，shape:rect/circle，axis:x/y/z，center、depth、size 或 diameter |
| reference | 包络 center、size、source，仅做直壁 AABB 初筛 |
| manufacturing | 工艺、材料和试片记录，不自动认证 |
| verification.dimension_tolerance_mm | 回读尺寸的数值比较阈值，不是配合公差 |
| preview / tools.blender / output_dir | 预览、可执行路径、输出根目录 |

开孔 axis 是刀具体穿透轴；size 是其横截面两维：x 对应 y/z，y 对应 x/z，z 对应 x/y。center 是装配世界坐标，depth 显式控制穿透，不误穿两面。检查刀具实际减少目标体积，但不证明接口包络通过。

enclosure.blend 保留装配。base.stl 和 lid.stl 分别移到打印 Z=0，build-report.json 记录变换。多边形圆角和直壁名义厚度不是所有局部壁厚的证据。

init/check/build/verify/mesh-check/package 命令见 SKILL.md。check 不要求 Blender；build 使用超时与日志，在参数和脚本签名目录生成新版本。只读 mesh-check 使用标准库，不改输入；它不验证完整装配或自交。

package 只收集明确清单：源工程、两件 STL、报告、必要预览、参数和 SHA256；不递归收集日志、账户或其他 CAD。示例尺寸为合成测试值，实际产品需重新核对单位、接口、材料、固定与配合。
