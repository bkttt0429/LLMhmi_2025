"""
GLB 模型結構分析器
使用 pygltflib 解析 GLB 文件並顯示詳細結構
"""

import os
import json
from pathlib import Path

try:
    from pygltflib import GLTF2
    HAS_PYGLTF = True
except ImportError:
    HAS_PYGLTF = False
    print("⚠️  未安裝 pygltflib，請執行: pip install pygltflib")

def analyze_glb(filepath):
    """分析 GLB 文件結構"""
    
    if not HAS_PYGLTF:
        print("❌ 需要安裝 pygltflib 庫")
        return
    
    print(f"📂 正在分析: {filepath}\n")
    
    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return
    
    # 載入 GLB
    gltf = GLTF2().load(filepath)
    
    print("=" * 60)
    print("📊 基本資訊")
    print("=" * 60)
    
    # 場景資訊
    print(f"場景數量: {len(gltf.scenes) if gltf.scenes else 0}")
    print(f"節點數量: {len(gltf.nodes) if gltf.nodes else 0}")
    print(f"Mesh 數量: {len(gltf.meshes) if gltf.meshes else 0}")
    print(f"材質數量: {len(gltf.materials) if gltf.materials else 0}")
    print(f"貼圖數量: {len(gltf.textures) if gltf.textures else 0}")
    print(f"動畫數量: {len(gltf.animations) if gltf.animations else 0}")
    
    # 檔案大小
    file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
    print(f"文件大小: {file_size:.2f} MB")
    
    print("\n" + "=" * 60)
    print("🌳 節點層級結構")
    print("=" * 60)
    
    # 遍歷場景
    if gltf.scenes:
        for scene_idx, scene in enumerate(gltf.scenes):
            print(f"\n場景 {scene_idx}:")
            if scene.nodes:
                for node_idx in scene.nodes:
                    print_node_tree(gltf, node_idx, depth=0)
    
    print("\n" + "=" * 60)
    print("🔷 Mesh 詳細資訊")
    print("=" * 60)
    
    if gltf.meshes:
        for mesh_idx, mesh in enumerate(gltf.meshes):
            print(f"\nMesh {mesh_idx}:")
            print(f"  名稱: {mesh.name if mesh.name else '(無名稱)'}")
            if mesh.primitives:
                for prim_idx, primitive in enumerate(mesh.primitives):
                    print(f"  Primitive {prim_idx}:")
                    if primitive.attributes:
                        print(f"    屬性: {', '.join(primitive.attributes.keys())}")
                    if primitive.material is not None:
                        mat = gltf.materials[primitive.material]
                        print(f"    材質: {mat.name if mat.name else f'Material_{primitive.material}'}")
    
    print("\n" + "=" * 60)
    print("🎨 材質資訊")
    print("=" * 60)
    
    if gltf.materials:
        for mat_idx, material in enumerate(gltf.materials):
            print(f"\n材質 {mat_idx}:")
            print(f"  名稱: {material.name if material.name else '(無名稱)'}")
            if material.pbrMetallicRoughness:
                pbr = material.pbrMetallicRoughness
                if pbr.baseColorFactor:
                    color = pbr.baseColorFactor
                    print(f"  基礎顏色: RGBA({color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f}, {color[3]:.2f})")
                if pbr.metallicFactor is not None:
                    print(f"  金屬度: {pbr.metallicFactor}")
                if pbr.roughnessFactor is not None:
                    print(f"  粗糙度: {pbr.roughnessFactor}")
    
    print("\n" + "=" * 60)
    print("🎯 關鍵節點偵測 (可能的關節)")
    print("=" * 60)
    
    keywords = ['base', 'shoulder', 'elbow', 'wrist', 'gripper', 'joint', 'arm', 'link']
    detected = []
    
    if gltf.nodes:
        for node_idx, node in enumerate(gltf.nodes):
            if node.name:
                name_lower = node.name.lower()
                for keyword in keywords:
                    if keyword in name_lower:
                        detected.append((node_idx, node.name, keyword))
                        break
    
    if detected:
        for node_idx, node_name, keyword in detected:
            print(f"  🎯 節點 {node_idx}: \"{node_name}\" (關鍵字: {keyword})")
    else:
        print("  ⚠️  未偵測到明顯的關節命名")
    
    print("\n" + "=" * 60)

def print_node_tree(gltf, node_idx, depth=0):
    """遞迴打印節點樹"""
    if node_idx >= len(gltf.nodes):
        return
    
    node = gltf.nodes[node_idx]
    indent = "│  " * depth + "├─ "
    
    # 節點名稱
    name = node.name if node.name else f"Node_{node_idx}"
    
    # 節點類型
    node_type = []
    if node.mesh is not None:
        mesh_name = gltf.meshes[node.mesh].name if gltf.meshes[node.mesh].name else f"Mesh_{node.mesh}"
        node_type.append(f"🔷 Mesh: {mesh_name}")
    if node.camera is not None:
        node_type.append("📷 Camera")
    if node.children:
        node_type.append(f"📁 {len(node.children)} 子節點")
    
    type_str = " | ".join(node_type) if node_type else "📦 空節點"
    
    print(f"{indent}{name} ({type_str})")
    
    # 變換資訊
    if node.translation or node.rotation or node.scale:
        if node.translation:
            print(f"{indent}   📍 位置: ({node.translation[0]:.3f}, {node.translation[1]:.3f}, {node.translation[2]:.3f})")
        if node.rotation:
            print(f"{indent}   🔄 旋轉: ({node.rotation[0]:.3f}, {node.rotation[1]:.3f}, {node.rotation[2]:.3f}, {node.rotation[3]:.3f})")
        if node.scale:
            print(f"{indent}   📏 縮放: ({node.scale[0]:.3f}, {node.scale[1]:.3f}, {node.scale[2]:.3f})")
    
    # 遞迴處理子節點
    if node.children:
        for child_idx in node.children:
            print_node_tree(gltf, child_idx, depth + 1)

if __name__ == "__main__":
    # 分析 eezybotarm.glb
    model_path = Path(__file__).parent.parent / "models" / "eezybotarm.glb"
    
    if model_path.exists():
        analyze_glb(str(model_path))
    else:
        print(f"❌ 找不到模型文件: {model_path}")
        print("\n請提供 GLB 文件路徑:")
        custom_path = input("> ")
        if custom_path and os.path.exists(custom_path):
            analyze_glb(custom_path)
        else:
            print("❌ 無效的路徑")
