"""Provides 'raw', which loads and parses raw KITTI data."""

import datetime as dt
import glob
import os
from collections import namedtuple

import numpy as np

# import pykitti.utils as utils
from pykitti import utils
from pykitti import tracklet as Tracklet

__author__ = "Lee Clement"
__email__ = "lee.clement@robotics.utias.utoronto.ca"


class raw:
    """Load and parse raw data into a usable format."""

    def __init__(self, base_path, date, drive, **kwargs):
        """Set the path and pre-load calibration data and timestamps."""
        self.drive = date + '_drive_' + drive + '_sync'
        self.calib_path = os.path.join(base_path, date)
        self.data_path = os.path.join(base_path, date, self.drive)
        self.frames = kwargs.get('frames', None)

        # Setting imformat='cv2' will convert the images to uint8 and BGR for
        # easy use with OpenCV.
        self.imformat = kwargs.get('imformat', None)

        # Pre-load data that isn't returned as a generator
        self._load_calib()
        self._load_timestamps()

    def __len__(self):
        """Return the number of frames loaded."""
        return len(self.timestamps)

    @property
    def oxts(self):
        """Generator to read OXTS data from file."""
        # Find all the data files
        oxts_path = os.path.join(self.data_path, 'oxts', 'data', '*.txt')
        oxts_files = sorted(glob.glob(oxts_path))

        # Subselect the chosen range of frames, if any
        if self.frames is not None:
            oxts_files = [oxts_files[i] for i in self.frames]

        # Return a generator yielding OXTS packets and poses
        return utils.get_oxts_packets_and_poses(oxts_files)

    @property
    def cam0(self):
        """Generator to read image files for cam0 (monochrome left)."""
        impath = os.path.join(self.data_path, 'image_00', 'data', '*.png')
        imfiles = sorted(glob.glob(impath))
        # Subselect the chosen range of frames, if any
        if self.frames is not None:
            imfiles = [imfiles[i] for i in self.frames]

        # Return a generator yielding the images
        return utils.get_images(imfiles, self.imformat)

    @property
    def cam1(self):
        """Generator to read image files for cam1 (monochrome right)."""
        impath = os.path.join(self.data_path, 'image_01', 'data', '*.png')
        imfiles = sorted(glob.glob(impath))
        # Subselect the chosen range of frames, if any
        if self.frames is not None:
            imfiles = [imfiles[i] for i in self.frames]

        # Return a generator yielding the images
        return utils.get_images(imfiles, self.imformat)

    @property
    def cam2(self):
        """Generator to read image files for cam2 (RGB left)."""
        impath = os.path.join(self.data_path, 'image_02', 'data', '*.png')
        imfiles = sorted(glob.glob(impath))
        # Subselect the chosen range of frames, if any
        if self.frames is not None:
            imfiles = [imfiles[i] for i in self.frames]

        # Return a generator yielding the images
        return utils.get_images(imfiles, self.imformat)

    @property
    def cam3(self):
        """Generator to read image files for cam0 (RGB right)."""
        impath = os.path.join(self.data_path, 'image_03', 'data', '*.png')
        imfiles = sorted(glob.glob(impath))
        # Subselect the chosen range of frames, if any
        if self.frames is not None:
            imfiles = [imfiles[i] for i in self.frames]

        # Return a generator yielding the images
        return utils.get_images(imfiles, self.imformat)

    @property
    def gray(self):
        """Generator to read monochrome stereo pairs from file.
        """
        return zip(self.cam0, self.cam1)

    @property
    def rgb(self):
        """Generator to read RGB stereo pairs from file.
        """
        return zip(self.cam2, self.cam3)

    @property
    def velo(self):
        """Generator to read velodyne [x,y,z,reflectance] scan data from binary files."""
        # Find all the Velodyne files
        velo_path = os.path.join(
            self.data_path, 'velodyne_points', 'data', '*.bin')
        velo_files = sorted(glob.glob(velo_path))

        # Subselect the chosen range of frames, if any
        if self.frames is not None:
            velo_files = [velo_files[i] for i in self.frames]

        # Return a generator yielding Velodyne scans.
        # Each scan is a Nx4 array of [x,y,z,reflectance]
        return utils.get_velo_scans(velo_files)

    def _load_calib_rigid(self, filename):
        """Read a rigid transform calibration file as a numpy.array."""
        filepath = os.path.join(self.calib_path, filename)
        data = utils.read_calib_file(filepath)
        return utils.transform_from_rot_trans(data['R'], data['T'])

    def _load_calib_cam_to_cam(self, velo_to_cam_file, cam_to_cam_file):
        # We'll return the camera calibration as a dictionary
        data = {}

        # Load the rigid transformation from velodyne coordinates
        # to unrectified cam0 coordinates
        T_cam0unrect_velo = self._load_calib_rigid(velo_to_cam_file)

        # Load and parse the cam-to-cam calibration data
        cam_to_cam_filepath = os.path.join(self.calib_path, cam_to_cam_file)
        filedata = utils.read_calib_file(cam_to_cam_filepath)

        # Create 3x4 projection matrices
        P_rect_00 = np.reshape(filedata['P_rect_00'], (3, 4))
        P_rect_10 = np.reshape(filedata['P_rect_01'], (3, 4))
        P_rect_20 = np.reshape(filedata['P_rect_02'], (3, 4))
        P_rect_30 = np.reshape(filedata['P_rect_03'], (3, 4))

        # Create 4x4 matrix from the rectifying rotation matrix
        R_rect_00 = np.eye(4)
        R_rect_00[0:3, 0:3] = np.reshape(filedata['R_rect_00'], (3, 3))

        # Compute the rectified extrinsics from cam0 to camN
        T0 = np.eye(4)
        T0[0, 3] = P_rect_00[0, 3] / P_rect_00[0, 0]
        T1 = np.eye(4)
        T1[0, 3] = P_rect_10[0, 3] / P_rect_10[0, 0]
        T2 = np.eye(4)
        T2[0, 3] = P_rect_20[0, 3] / P_rect_20[0, 0]
        T3 = np.eye(4)
        T3[0, 3] = P_rect_30[0, 3] / P_rect_30[0, 0]

        # Compute the velodyne to rectified camera coordinate transforms
        data['T_cam0_velo'] = T0.dot(R_rect_00.dot(T_cam0unrect_velo))
        data['T_cam1_velo'] = T1.dot(R_rect_00.dot(T_cam0unrect_velo))
        data['T_cam2_velo'] = T2.dot(R_rect_00.dot(T_cam0unrect_velo))
        data['T_cam3_velo'] = T3.dot(R_rect_00.dot(T_cam0unrect_velo))

        # Compute the camera intrinsics
        data['K_cam0'] = P_rect_00[0:3, 0:3]
        data['K_cam1'] = P_rect_10[0:3, 0:3]
        data['K_cam2'] = P_rect_20[0:3, 0:3]
        data['K_cam3'] = P_rect_30[0:3, 0:3]

        # Compute the stereo baselines in meters by projecting the origin of
        # each camera frame into the velodyne frame and computing the distances
        # between them
        p_cam = np.array([0, 0, 0, 1])
        p_velo0 = np.linalg.inv(data['T_cam0_velo']).dot(p_cam)
        p_velo1 = np.linalg.inv(data['T_cam1_velo']).dot(p_cam)
        p_velo2 = np.linalg.inv(data['T_cam2_velo']).dot(p_cam)
        p_velo3 = np.linalg.inv(data['T_cam3_velo']).dot(p_cam)

        data['b_gray'] = np.linalg.norm(p_velo1 - p_velo0)  # gray baseline
        data['b_rgb'] = np.linalg.norm(p_velo3 - p_velo2)  # rgb baseline

        return data

    def _load_calib(self):
        """Load and compute intrinsic and extrinsic calibration parameters."""
        # We'll build the calibration parameters as a dictionary, then
        # convert it to a namedtuple to prevent it from being modified later
        data = {}

        # Load the rigid transformation from velodyne to IMU
        data['T_velo_imu'] = self._load_calib_rigid('calib_imu_to_velo.txt')

        # Load the camera intrinsics and extrinsics
        data.update(self._load_calib_cam_to_cam(
            'calib_velo_to_cam.txt', 'calib_cam_to_cam.txt'))

        # Pre-compute the IMU to rectified camera coordinate transforms
        data['T_cam0_imu'] = data['T_cam0_velo'].dot(data['T_velo_imu'])
        data['T_cam1_imu'] = data['T_cam1_velo'].dot(data['T_velo_imu'])
        data['T_cam2_imu'] = data['T_cam2_velo'].dot(data['T_velo_imu'])
        data['T_cam3_imu'] = data['T_cam3_velo'].dot(data['T_velo_imu'])

        self.calib = namedtuple('CalibData', data.keys())(*data.values())

    def _load_timestamps(self):
        """Load timestamps from file."""
        timestamp_file = os.path.join(
            self.data_path, 'oxts', 'timestamps.txt')

        # Read and parse the timestamps
        self.timestamps = []
        with open(timestamp_file, 'r') as f:
            for line in f.readlines():
                # NB: datetime only supports microseconds, but KITTI timestamps
                # give nanoseconds, so need to truncate last 4 characters to
                # get rid of \n (counts as 1) and extra 3 digits
                t = dt.datetime.strptime(line[:-4], '%Y-%m-%d %H:%M:%S.%f')
                self.timestamps.append(t)

        # Subselect the chosen range of frames, if any
        if self.frames is not None:
            self.timestamps = [self.timestamps[i] for i in self.frames]

    def parseTrackletXml(self):
        objs_frame_wise = {}
        ObjTuple = namedtuple('obj', 'id, type, bbox, location, orientation, frameNum')
        xml_path = os.path.join(self.data_path, 'tracklet_labels.xml')
        if os.path.isfile(xml_path):
            tracklets = Tracklet.parseXML(xml_path)
            for id, tracklet in enumerate(tracklets):
                print ('tracklet {0: 3d}: {1}'.format(id, tracklet))
                # this part is inspired by kitti object development kit matlab code: computeBox3D
                h, w, l = tracklet.size
                # in velodyne coordinates around zero point and without orientation yet\
                bbox = np.array([[l / 2, l / 2, -l / 2, -l / 2, l / 2, l / 2, -l / 2, -l / 2],
                                 [w / 2, -w / 2, -w / 2, w / 2, w / 2, -w / 2, -w / 2, w / 2],
                                 [0.0, 0.0, 0.0, 0.0, h, h, h, h]])
                for translation, rotation, state, occlusion, truncation, amtOcclusion, amtBorders, absoluteFrameNumber in tracklet:
                    if truncation not in (Tracklet.TRUNC_IN_IMAGE, Tracklet.TRUNC_TRUNCATED):
                        continue
                    # re-create 3D bounding box in velodyne coordinate system
                    yaw = rotation[2]  # other rotations are 0 in all xml files I checked
                    assert np.abs(rotation[:2]).sum() == 0, 'object rotations other than yaw given!'
                    rotMat = np.array([[np.cos(yaw), -np.sin(yaw), 0.0],
                                       [np.sin(yaw), np.cos(yaw), 0.0],
                                       [0.0, 0.0, 1.0]])
                    bbox = np.dot(rotMat, bbox) + np.tile(translation, (8, 1))
                    obj_ = ObjTuple(id, tracklet.objectType, bbox, translation, rotation, absoluteFrameNumber)
                    if absoluteFrameNumber in objs_frame_wise.keys():
                        objs_frame_wise[absoluteFrameNumber].append(obj_)
                    else:
                        objs_frame_wise[absoluteFrameNumber] = [obj_]
        return objs_frame_wise


if __name__ == '__main__':
    base_path = '/media/jianyun/My Passport/KITTI_DATA/RawData/Data'
    date = '2011_09_26'
    drive = '0001'
    test_raw = raw(base_path, date, drive)
    test_raw.parseTrackletXml()
