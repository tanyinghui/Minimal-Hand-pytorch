import cv2
import time
import open3d
import torch
from manopth import manolayer
from model.detnet import detnet
from utils import func, bone, AIK, smoother
import numpy as np
import matplotlib.pyplot as plt
from utils import vis
from op_pso import PSO

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
_mano_root = 'mano/models'

module = detnet().to(device)
print('load model start')
check_point = torch.load('bmc_ckp.pth', map_location=device)
model_state = module.state_dict()
state = {}
for k, v in check_point.items():
    if k in model_state:
        state[k] = v
    else:
        print(k, ' is NOT in current model')
model_state.update(state)
module.load_state_dict(model_state)
print('load model finished')
pose, shape = func.initiate("zero")
pose = pose.to(device)
shape = shape.to(device)
pre_useful_bone_len = np.zeros((1, 15))
pose0 = torch.eye(3).repeat(1, 16, 1, 1)
pose0 = pose0.to(device)
mano = manolayer.ManoLayer(flat_hand_mean=True,
                           side="right",
                           mano_root=_mano_root,
                           use_pca=False,
                           root_rot_mode='rotmat',
                           joint_rot_mode='rotmat')
mano = mano.to(device)
print('start opencv')
point_fliter = smoother.OneEuroFilter(4.0, 0.0)
mesh_fliter = smoother.OneEuroFilter(4.0, 0.0)
shape_fliter = smoother.OneEuroFilter(4.0, 0.0)
cap = cv2.VideoCapture("test.MOV")
fps = cap.get(cv2.CAP_PROP_FPS)
print(f"video clip fps: {fps}")
print('opencv finished')
flag = 1
plt.ion()
f = plt.figure()

fliter_ax = f.add_subplot(111, projection='3d')
# plt.show()
view_mat = np.array([[1.0, 0.0, 0.0],
                     [0.0, -1.0, 0],
                     [0.0, 0, -1.0]])
mesh = open3d.geometry.TriangleMesh()
hand_verts, j3d_recon = mano(pose0, shape.float())
mesh.triangles = open3d.utility.Vector3iVector(mano.th_faces.cpu())
hand_verts = hand_verts.clone().detach().cpu().numpy()[0]
mesh.vertices = open3d.utility.Vector3dVector(hand_verts)
# viewer = open3d.visualization.Visualizer()
# viewer.create_window(width=480, height=480, window_name='mesh')
# viewer.add_geometry(mesh)
# viewer.update_renderer()

print('start pose estimate..')

pre_uv = None
shape_time = 0
opt_shape = None
shape_flag = True
# Start time
start = time.time()
while (cap.isOpened()):
    
    ret_flag, img = cap.read()
    if ret_flag != True:
        break
    input = np.flip(img.copy(), -1)
    # k = cv2.waitKey(1) & 0xFF
    if input.shape[0] > input.shape[1]:
        margin = (input.shape[0] - input.shape[1]) // 2
        input = input[margin:-margin]
    else:
        margin = (input.shape[1] - input.shape[0]) // 2
        input = input[:, margin:-margin]
    img = input.copy()
    img = np.flip(img, -1)
    # cv2.imshow("Capture_Test", img)
    input = cv2.resize(input, (128, 128))
    input = torch.tensor(input.transpose([2, 0, 1]), dtype=torch.float, device=device)  # hwc -> chw
    input = func.normalize(input, [0.5, 0.5, 0.5], [1, 1, 1])
    result = module(input.unsqueeze(0))

    pre_joints = result['xyz'].squeeze(0)
    now_uv = result['uv'].clone().detach().cpu().numpy()[0, 0]
    now_uv = now_uv.astype(np.float)
    trans = np.zeros((1, 3))
    trans[0, 0:2] = now_uv - 16.0
    trans = trans / 16.0
    new_tran = np.array([[trans[0, 1], trans[0, 0], trans[0, 2]]])
    pre_joints = pre_joints.clone().detach().cpu().numpy()

    flited_joints = point_fliter.process(pre_joints)

    fliter_ax.cla()

    filted_ax = vis.plot3d(flited_joints + new_tran, fliter_ax)
    pre_useful_bone_len = bone.caculate_length(pre_joints, label="useful")

    NGEN = 100
    popsize = 100
    low = np.zeros((1, 10)) - 3.0
    up = np.zeros((1, 10)) + 3.0
    parameters = [NGEN, popsize, low, up]
    pso = PSO(parameters, pre_useful_bone_len.reshape((1, 15)),_mano_root)
    pso.main()
    opt_shape = pso.ng_best
    opt_shape = shape_fliter.process(opt_shape)

    opt_tensor_shape = torch.tensor(opt_shape, dtype=torch.float)
    opt_tensor_shape = opt_tensor_shape.to(device)
    _, j3d_p0_ops = mano(pose0, opt_tensor_shape)
    template = j3d_p0_ops.cpu().numpy().squeeze(0) / 1000.0  # template, m 21*3
    ratio = np.linalg.norm(template[9] - template[0]) / np.linalg.norm(pre_joints[9] - pre_joints[0])
    j3d_pre_process = pre_joints * ratio  # template, m
    j3d_pre_process = j3d_pre_process - j3d_pre_process[0] + template[0]
    pose_R = AIK.adaptive_IK(template, j3d_pre_process)
    pose_R = torch.from_numpy(pose_R).float()
    #  reconstruction
    pose_R = pose_R.to(device)
    hand_verts, j3d_recon = mano(pose_R, opt_tensor_shape.float())
    mesh.triangles = open3d.utility.Vector3iVector(mano.th_faces.cpu())
    hand_verts = hand_verts.clone().detach().cpu().numpy()[0]
    hand_verts = mesh_fliter.process(hand_verts)
    hand_verts = np.matmul(view_mat, hand_verts.T).T
    hand_verts[:, 0] = hand_verts[:, 0] - 50
    hand_verts[:, 1] = hand_verts[:, 1] - 50
    mesh_tran = np.array([[-new_tran[0, 0], new_tran[0, 1], new_tran[0, 2]]])
    hand_verts = hand_verts - 100 * mesh_tran

    mesh.vertices = open3d.utility.Vector3dVector(hand_verts)
    mesh.paint_uniform_color([228 / 255, 178 / 255, 148 / 255])
    mesh.compute_triangle_normals()
    mesh.compute_vertex_normals()
    # viewer.update_geometry(mesh)
    # viewer.poll_events()
cap.release()
# cv2.destroyAllWindows()
# End time
end = time.time()
# Time elapsed
elapsed_time = end - start
print (f"Time taken : {elapsed_time} seconds")
