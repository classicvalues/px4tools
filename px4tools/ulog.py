"""
ulog2pandas converter
"""

#pylint: disable=no-member, invalid-name, broad-except, too-many-locals

from __future__ import print_function

import os
import tempfile
import re
import glob
import shutil
import pickle

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyulog
import transforms3d.taitbryan as tf

IEKF_STATES = {
    0: 'q_nb_0',
    1: 'q_nb_1',
    2: 'q_nb_2',
    3: 'q_nb_3',
    4: 'vel_N',
    5: 'vel_E',
    6: 'vel_D',
    7: 'gyro_bias_bx',
    8: 'gyro_bias_by',
    9: 'gyro_bias_bz',
    10: 'accel_scale',
    11: 'pos_N',
    12: 'pos_E',
    13: 'pos_D',
    14: 'terrain_alt',
    15: 'baro_bias',
    16: 'wind_N',
    17: 'wind_E',
    18: 'wind_D',
}

IEKF_ERROR_STATES = {
    0: 'rot_N',
    1: 'rot_E',
    2: 'rot_D',
    3: 'vel_N',
    4: 'vel_E',
    5: 'vel_D',
    6: 'gyro_bias_N',
    7: 'gyro_bias_E',
    8: 'gyro_bias_D',
    9: 'accel_scale',
    10: 'pos_N',
    11: 'pos_E',
    12: 'pos_D',
    13: 'terrain_alt',
    14: 'baro_bias',
    15: 'wind_N',
    16: 'wind_E',
    17: 'wind_D',
}

def compute_data(df):
    """
    This computes useful data from analysis from the raw log data,
    converting quaternions to euler angles etc.
    """
    series = [df]
    msg = 't_vehicle_attitude_0'
    roll, pitch, yaw = series_quat2euler(
        df.t_vehicle_attitude_0__f_q_0_,
        df.t_vehicle_attitude_0__f_q_1_,
        df.t_vehicle_attitude_0__f_q_2_,
        df.t_vehicle_attitude_0__f_q_3_, msg)
    series += [roll, pitch, yaw]

    try:
        msg_gt = 't_vehicle_attitude_groundtruth_0'
        roll_gt, pitch_gt, yaw_gt = series_quat2euler(
            df.t_vehicle_attitude_groundtruth_0__f_q_0_,
            df.t_vehicle_attitude_groundtruth_0__f_q_1_,
            df.t_vehicle_attitude_groundtruth_0__f_q_2_,
            df.t_vehicle_attitude_groundtruth_0__f_q_3_, msg_gt)

        e_roll = pd.Series(angle_wrap(roll - roll_gt), name=msg + '__f_roll_error')
        e_pitch = pd.Series(angle_wrap(pitch - pitch_gt), name=msg + '__f_pitch_error')
        e_yaw = pd.Series(angle_wrap(yaw - yaw_gt), name=msg + '__f_yaw_error')

        series += [roll_gt, pitch_gt, yaw_gt, e_roll, e_pitch, e_yaw]
    except Exception as ex:
        print(ex)

    return pd.concat(series, axis=1)

def angle_wrap(x):
    """wrap angle betwe -pi and pi"""
    return np.arcsin(np.sin(x))

def plot_altitude(df, plot_groundtruth=False):
    """
    Plot altitude
    """
    plt.title('altitude')
    df.t_vehicle_global_position_0__f_alt.plot(label='alt', style='b-')
    if plot_groundtruth:
        df.t_vehicle_global_position_groundtruth_0__f_alt.plot(
            label='alt-true', style='b--')
    plt.grid()
    plt.legend(loc='best', ncol=3)
    plt.xlabel('t, sec')
    plt.ylabel('m')

def plot_iekf_std_dev(df):
    """
    Plot IEKF standard deviation.
    """
    #pylint: disable=exec-used, unused-argument
    for i in range(len(IEKF_ERROR_STATES)):
        exec('np.sqrt(df.t_estimator_status_0__f_covariances_{:d}_).'
             'plot(label=IEKF_ERROR_STATES[{:d}])'.format(i, i))
    plt.gca().set_ylim(0, 4)
    plt.legend(ncol=3, loc='best')
    plt.title('IEKF est std. dev.')
    plt.grid()

def plot_iekf_states(df):
    """
    Plot IEKF states
    """
    #pylint: disable=exec-used, unused-argument
    for i in range(len(IEKF_STATES)):
        exec('df.t_estimator_status_0__f_states_{:d}_.plot(label=IEKF_STATES[{:d}])'.format(i, i))
    plt.legend(ncol=3, loc='best')
    plt.title('IEKF states')
    plt.grid()

def plot_local_position(df, plot_groundtruth=False):
    """
    Plot local position
    """
    plt.title('local position')
    plt.plot(df.t_vehicle_local_position_0__f_x,
             df.t_vehicle_local_position_0__f_y, label='estimate')
    if plot_groundtruth:
        plt.plot(df.t_vehicle_local_position_groundtruth_0__f_x,
                 df.t_vehicle_local_position_groundtruth_0__f_y, 'r--',
                 label='true')
    plt.grid()
    plt.xlabel('N, m')
    plt.ylabel('E, m')
    plt.legend(loc='best')

def plot_euler(df, plot_groundtruth=False):
    """
    Plot euler angles
    """
    plt.title('euler angles')
    np.rad2deg(df.t_vehicle_attitude_0__f_roll).plot(label='roll', style='r-')
    if plot_groundtruth:
        np.rad2deg(df.t_vehicle_attitude_groundtruth_0__f_roll).plot(
            label='roll true', style='r--')
    np.rad2deg(df.t_vehicle_attitude_0__f_pitch).plot(label='pitch', style='g-')
    if plot_groundtruth:
        np.rad2deg(df.t_vehicle_attitude_groundtruth_0__f_pitch).plot(
            label='pitch true', style='g--')
    np.rad2deg(df.t_vehicle_attitude_0__f_yaw).plot(label='yaw', style='b-')
    if plot_groundtruth:
        np.rad2deg(df.t_vehicle_attitude_groundtruth_0__f_yaw).plot(
            label='yaw true', style='b--')
    plt.grid()
    plt.legend(loc='best', ncol=3)
    plt.xlabel('t, sec')
    plt.ylabel('deg')

def plot_euler_error(df):
    """
    Plot error between euler angles and ground truth
    """
    plt.title('euler angle errors')
    np.rad2deg(df.t_vehicle_attitude_0__f_roll_error).plot(
        label='roll error', style='r-')
    np.rad2deg(df.t_vehicle_attitude_0__f_pitch_error).plot(
        label='pitch error', style='g-')
    np.rad2deg(df.t_vehicle_attitude_0__f_yaw_error).plot(
        label='yaw error', style='b-')
    plt.grid()
    plt.legend(loc='best', ncol=3)
    plt.xlabel('t, sec')
    plt.ylabel('deg')

def plot_velocity(df, plot_groundtruth=False):
    """
    Plot velocity
    """
    plt.title('velocity')
    df.t_vehicle_global_position_0__f_vel_n.plot(label='vel_n', style='r-')
    if plot_groundtruth:
        df.t_vehicle_global_position_groundtruth_0__f_vel_n.plot(
            label='vel_n-true', style='r--')
    df.t_vehicle_global_position_0__f_vel_e.plot(
        label='vel_e', style='g-')
    if plot_groundtruth:
        df.t_vehicle_global_position_groundtruth_0__f_vel_e.plot(
            label='vel_e-true', style='g--')
    df.t_vehicle_global_position_0__f_vel_d.plot(
        label='vel_d', style='b-')
    if plot_groundtruth:
        df.t_vehicle_global_position_groundtruth_0__f_vel_d.plot(
            label='vel_d-true', style='b--')
    plt.grid()
    plt.legend(loc='best', ncol=3)
    plt.xlabel('t, sec')
    plt.ylabel('m/s')

def series_quat2euler(q0, q1, q2, q3, msg_name):
    """
    Given pandas series q0-q4, compute series roll, pitch, yaw
    """
    yaw, pitch, roll = np.array([
        tf.quat2euler([q0i, q1i, q2i, q3i]) for
        q0i, q1i, q2i, q3i in zip(q0, q1, q2, q3)]).T
    yaw = pd.Series(name=msg_name + '__f_yaw', data=yaw, index=q0.index)
    pitch = pd.Series(name=msg_name + '__f_pitch', data=pitch, index=q0.index)
    roll = pd.Series(name=msg_name + '__f_roll', data=roll, index=q0.index)
    return roll, pitch, yaw

def estimator_analysis(df, plot=True):
    """
    Evaluates estimator performance
    """
    #pylint: disable=unused-variable
    data = {
        'roll_error_mean' : np.rad2deg(
            df.t_vehicle_attitude_0__f_roll_error.mean()),
        'pitch_error_mean' : np.rad2deg(
            df.t_vehicle_attitude_0__f_pitch_error.mean()),
        'yaw_error_mean' : np.rad2deg(
            df.t_vehicle_attitude_0__f_yaw_error.mean()),
        'roll_error_std' : np.rad2deg(np.sqrt(
            df.t_vehicle_attitude_0__f_roll_error.var())),
        'pitch_error_std' : np.rad2deg(np.sqrt(
            df.t_vehicle_attitude_0__f_pitch_error.var())),
        'yaw_error_std' : np.rad2deg(np.sqrt(
            df.t_vehicle_attitude_0__f_yaw_error.var())),
    }
    if plot:
        print('''
ESTIMATOR ANALYSIS
-----------------------------------
mean euler error:
\t{roll_error_mean:10f}\t deg
\t{pitch_error_mean:10f}\t deg
\t{yaw_error_mean:10f}\t deg

standard deviation euler error:
\t{roll_error_std:10f}\t deg
\t{pitch_error_std:10f}\t deg
\t{yaw_error_std:10f}\t deg
'''.format(**data))

        plt.figure()
        plot_altitude(df, plot_groundtruth=True)

        plt.figure()
        plot_euler(df, plot_groundtruth=True)

        plt.figure()
        plot_euler_error(df)

        plt.figure()
        plot_local_position(df, plot_groundtruth=True)

        plt.figure()
        plot_velocity(df, plot_groundtruth=True)

    return data

class PX4MessageDict(dict):

    """
    PX4 has several data frames in a log and they don't all have the same
    index, so this structure is used to manipulate the resulting dictionary
    of dataframes that a log produces.
    """

    def __init__(self, d):
        super(PX4MessageDict, self).__init__(d)
        for topic in self.keys():
            new_cols = {}
            for col in self[topic].columns:
                if col == 'timestamp':
                    new_cols[col] = col
                else:
                    new_cols[col] = 't_' + topic + '__f_' + col
            df = self[topic].rename(columns=new_cols)
            df.index = pd.TimedeltaIndex(df.timestamp*1e3, unit='ns')
            self[topic] = df

    def concat(self, topics=None, on=None, dt=None, verbose=False):
        """

        @param topics: topics to merge on, unspecified merges all

        timestamp options
        @param on: the topic whose timestamp will define the merge timestamp
        @param dt: if specified, dt cannot be specified

        @param verbose: show status
        """
        # define timestamps to merge on
        if dt is not None:
            ts_min = None
            ts_max = None
            for topic in sorted(self.keys()):
                ts_t_min = self[topic]['timestamp'].min()
                ts_t_max = self[topic]['timestamp'].max()
                if ts_min is None or ts_t_min < ts_min:
                    ts_min = ts_t_min
                if ts_max is None or ts_t_max > ts_max:
                    ts_max = ts_t_max
            timestamps = np.arange(ts_min, ts_max - dt*1e6, dt*1e6, dtype=np.int64)
        elif on is not None:
            timestamps = self[on].timestamp
        else:
            raise IOError('must pass dt or on')

        # concat
        m = pd.DataFrame(data=timestamps, columns=['timestamp'])
        if topics is None:
            topics = self.keys()
        for topic in topics:
            if verbose:
                print('merging {:s} as of timestamp'.format(topic))
            df = self[topic]
            m = pd.merge_asof(m, df, 'timestamp')
        m.index = pd.TimedeltaIndex(m.timestamp*1e3, unit='ns')
        # fill any nans
        m.ffill(inplace=True)
        m.bfill(inplace=True)
        m.pad(inplace=True)
        assert(np.all(np.isfinite(m)))
        return m

def read_ulog(ulog_filename, messages='', verbose=False):
    """
    Convert ulog to pandas dataframe.
    """

    tmp_dir = tempfile.mkdtemp()
    pyulog.ulog2csv.convert_ulog2csv(
        ulog_filename, messages, tmp_dir, ',')
    log_name = os.path.splitext(os.path.basename(ulog_filename))[0]
    data = {}
    glob_expr = '{:s}*.csv'.format(
        os.path.join(tmp_dir, log_name))

    # column naming
    d_col_rename = {
        '[': '_',
        ']': '_',
    }
    col_rename_pattern = re.compile(
        r'(' + '|'.join([re.escape(key) for key in d_col_rename.keys()]) + r')')

    for filename in sorted(glob.glob(glob_expr)):
        if verbose:
            print('processing', filename)
        file_name = os.path.splitext(os.path.basename(filename))[0]
        topic_name = file_name.replace(log_name + '_', '')

        # read data
        data_new = pd.read_csv(filename)
        data_new.columns = [
            col_rename_pattern.sub(
                lambda x: d_col_rename[x.group()], col)
            for col in data_new.columns
        ]

        data[topic_name] = data_new

    if verbose:
        print(log_name, 'data loaded')

    shutil.rmtree(tmp_dir)
    return PX4MessageDict(data)

def _smallest_positive_real_root(roots, min_val=0, max_val=1e6):
    """
    Find smallest positive real root in list
    """
    res = 0
    if len(roots) > 0:
        cond = np.logical_and(
            np.isreal(roots),
            np.real(roots) > min_val)
        posreal = sorted(np.real(roots[cond]))
        if len(posreal) > 0:
            res = posreal[0]
    if not np.isfinite(res) or res < min_val or res > max_val:
        res = np.nan
    return res

def plot_allan_std_dev(data, plot=True, plot_deriv=False, min_intervals=9, poly_order=2):
    """
    Given a dataset of a stationary vehicle on the ground,
    this compute the Allan standard deviation plot for the noise.
    """
    #pylint: disable=too-many-statements

    data.index = pd.TimedeltaIndex(data.index, unit='s')
    dt = float(
        data.index.values[1] - data.index.values[0])/1e9

    data_vals = []
    dt_vals = []
    c = int(np.ceil(np.log10(dt)))
    c_vals = []
    # require at least 9 clusters for < 25% error:
    # source http://www.afahc.ro/ro/afases/2014/mecanica/marinov_petrov_allan.pdf
    t_len = (data.index.values[-1] - data.index.values[0])/1e9
    while 10**c < float(t_len/min_intervals):
        c_vals += [10**c]
        c += 0.2
    for c_i in c_vals:
        allan_std = float(np.sqrt(data.resample(
            '{:d}L'.format(int(c_i*1000))).agg('mean').diff().var()/2))
        if not np.isfinite(allan_std):
            break
        data_vals += [allan_std]
        dt_vals += [c_i]

    x = np.log10(dt_vals)
    y = np.log10(data_vals)

    p = np.polynomial.Polynomial.fit(x, y, poly_order)
    pdiff = p.deriv()

    log_tau_0 = _smallest_positive_real_root((pdiff + 0.5).roots(), 0, 5)
    tau_0 = 10**log_tau_0
    if tau_0 > 0 and np.isfinite(tau_0):
        sig_rw = 10**p(log_tau_0)*np.sqrt(tau_0)
    else:
        print('failed to find tau_0')
        sig_rw = np.nan

    log_tau_1 = _smallest_positive_real_root((pdiff).roots(), log_tau_0, 5)
    tau_1 = 10**log_tau_1
    if tau_1 > 0 and np.isfinite(tau_1):
        sig_bi = (10**p(log_tau_1))*np.sqrt(np.pi/(2*np.log(2)))
    else:
        print('failed to find tau_1')
        sig_bi = np.nan

    log_tau_2 = _smallest_positive_real_root((pdiff - 0.5).roots(), log_tau_1, 5)
    tau_2 = 10**log_tau_2
    if tau_2 > 0 and np.isfinite(tau_2):
        sig_rrw = (10**p(log_tau_2))*np.sqrt(3/tau_2)
    else:
        print('failed to find tau_2')
        sig_rrw = np.nan

    if plot:
        x2 = np.linspace(
            min([x[0], log_tau_0, log_tau_1, log_tau_2]),
            max([x[-1], log_tau_0, log_tau_1, log_tau_2]))
        y2 = p(x2)
        plt.title('Frequency Stability')
        plt.loglog(dt_vals, data_vals, '.', label='raw')
        plt.xlabel('Averaging Time, $\\tau$, sec')
        plt.ylabel('Allan Deviation $\\sigma(\\tau)$')
        plt.loglog(10**x2, 10**y2, '-', label='fit')
        if plot_deriv:
            ydiff = pdiff(x2)
            plt.loglog(10**x2, 10**ydiff, '--', label='fit deriv')
        plt.plot(tau_0, 10**p(log_tau_0), 'rx', label='$\\sigma_{rw}$', markeredgewidth=3)
        plt.plot(tau_1, 10**p(log_tau_1), 'bx', label='$\\sigma_{bi}$', markeredgewidth=3)
        plt.plot(tau_2, 10**p(log_tau_2), 'gx', label='$\\sigma_{rrw}$', markeredgewidth=3)
        plt.grid(True, which='both')
        plt.minorticks_on()

    return {
        'sig_rw': sig_rw,
        'sig_bi': sig_bi,
        'sig_rrw': sig_rrw,
        'tau_0': tau_0,
        'tau_1': tau_1,
        'tau_2': tau_2
    }

def plot_autocorrelation(data, plot=True, poly_order=5):
    """
    Given a dataset of a stationary vehicle on the ground,
    this compute the autocorrellation. The intersection with
    the horizontal line at 0.348 represents the correllation
    time constant. If the intersection does not occur, it
    indicates that the random walk process is not significant
    and is over powered by wide-band noise.
    """
    data.index = pd.TimedeltaIndex(data.index, unit='s')
    data_vals = []
    dt_vals = []
    dt = 1
    # downsample every dt seconds, taking mean
    data = data.resample(
        '{:d}L'.format(int(dt*1000))).agg('mean')
    lag_max = int(dt*len(data.index)/2)
    for i in range(1, int(lag_max/dt)):
        data_vals += [data.autocorr(i)]
        dt_vals += [i*dt]

    # polynomial fits
    p = np.polynomial.Polynomial.fit(dt_vals, data_vals, poly_order)

    # normalize by max of fit polynomial
    x = np.linspace(0, lag_max)
    y = p(x)
    y_max = np.max(np.abs(y))
    data_vals /= y_max
    y /= y_max
    p /= y_max

    if plot:
        plt.title('normalized autocorrelation')
        plt.plot(dt_vals[1:], data_vals[1:], '.', alpha=0.2, label='raw')
        plt.xlabel('lag, sec')
        plt.ylabel('corr/ max(corr)')
        plt.plot(x, y, linewidth=2, label='fit')
        plt.hlines(1/np.e, 0, lag_max, linewidth=2)
        plt.gca().set_ylim(-1, 1)
        plt.gca().set_xlim(0, lag_max)
        plt.grid(True)

    correlation_time = _smallest_positive_real_root((p - 1/np.e).roots())
    return correlation_time

def noise_analysis_sensor(df, topic='sensor_gyro_0', plot=True, allan_args={},
        corr_args={}):
    """
    Given a sensor gyro dataset of a stationary vehicle on the ground,
    this compute the noise statistics.
    """

    r = {}

    # gyroscope
    plt.figure()
    gx = df['t_{:s}__f_x'.format(topic)]
    gy = df['t_{:s}__f_y'.format(topic)]
    gz = df['t_{:s}__f_z'.format(topic)]
    tau1 = plot_autocorrelation(gx, plot, **corr_args)
    handles, labels = plt.gca().get_legend_handles_labels()
    tau2 = plot_autocorrelation(gy, plot, **corr_args)
    tau3 = plot_autocorrelation(gz, plot, **corr_args)
    plt.title('normalized autocorrelation - {:s}'.format(topic))
    plt.legend(handles, labels, loc='best', ncol=3)
    r['{:s}_randomwalk_correlation_time'.format(topic)] = [tau1, tau2, tau3]

    plt.figure()
    res1 = plot_allan_std_dev(gx, plot, **allan_args)
    handles, labels = plt.gca().get_legend_handles_labels()
    res2 = plot_allan_std_dev(gy, plot, **allan_args)
    res3 = plot_allan_std_dev(gz, plot, **allan_args)
    plt.title('Allan variance plot - {:s}'.format(topic))
    plt.legend(handles, labels, loc='best', ncol=3)
    for key in res1.keys():
        r['{:s}_{:s}'.format(topic, key)] = [d[key] for d in [res1, res2, res3]]
    return r

def noise_analysis_sensor_combined(df, plot=True):
    """
    Given a sensor combined dataset of a stationary vehicle on the ground,
    this compute the noise statistics.
    """
    #pylint: disable=too-many-statements

    r = {}

    # gyroscope
    plt.figure()
    tau1 = plot_autocorrelation(df.t_sensor_combined_0__f_gyro_rad_0_, plot)
    handles, labels = plt.gca().get_legend_handles_labels()
    tau2 = plot_autocorrelation(df.t_sensor_combined_0__f_gyro_rad_1_, plot)
    tau3 = plot_autocorrelation(df.t_sensor_combined_0__f_gyro_rad_2_, plot)
    plt.title('normalized autocorrelation - gyroscope')
    plt.legend(handles, labels, loc='best', ncol=3)
    r['gyroscope_randomwalk_correlation_time'] = [tau1, tau2, tau3]

    plt.figure()
    res1 = plot_allan_std_dev(df.t_sensor_combined_0__f_gyro_rad_0_, plot)
    handles, labels = plt.gca().get_legend_handles_labels()
    res2 = plot_allan_std_dev(df.t_sensor_combined_0__f_gyro_rad_1_, plot)
    res3 = plot_allan_std_dev(df.t_sensor_combined_0__f_gyro_rad_2_, plot)
    plt.title('Allan variance plot - gyroscope')
    plt.legend(handles, labels, loc='best', ncol=3)
    for key in res1.keys():
        r['gyroscope_' + key] = [d[key] for d in [res1, res2, res3]]

    # accelerometer
    plt.figure()
    tau1 = plot_autocorrelation(df.t_sensor_combined_0__f_accelerometer_m_s2_0_, plot)
    handles, labels = plt.gca().get_legend_handles_labels()
    tau2 = plot_autocorrelation(df.t_sensor_combined_0__f_accelerometer_m_s2_1_, plot)
    tau3 = plot_autocorrelation(df.t_sensor_combined_0__f_accelerometer_m_s2_2_, plot)
    plt.title('normalized autocorrelation - accelerometer')
    plt.legend(handles, labels, loc='best', ncol=3)
    r['accelerometer_randomwalk_correlation_time'] = [tau1, tau2, tau3]

    plt.figure()
    res1 = plot_allan_std_dev(df.t_sensor_combined_0__f_accelerometer_m_s2_0_, plot)
    handles, labels = plt.gca().get_legend_handles_labels()
    res2 = plot_allan_std_dev(df.t_sensor_combined_0__f_accelerometer_m_s2_1_, plot)
    res3 = plot_allan_std_dev(df.t_sensor_combined_0__f_accelerometer_m_s2_2_, plot)
    res = np.array([res1, res2, res3])
    plt.title('Allan variance plot - accelerometer')
    plt.legend(handles, labels, loc='best', ncol=3)
    for key in res1.keys():
        r['accelerometer_' + key] = [d[key] for d in [res1, res2, res3]]

    # magnetometer
    plt.figure()
    tau1 = plot_autocorrelation(df.t_sensor_combined_0__f_magnetometer_ga_0_, plot)
    handles, labels = plt.gca().get_legend_handles_labels()
    tau2 = plot_autocorrelation(df.t_sensor_combined_0__f_magnetometer_ga_1_, plot)
    tau3 = plot_autocorrelation(df.t_sensor_combined_0__f_magnetometer_ga_2_, plot)
    plt.title('normalized autocorrelation - magnetometer')
    plt.legend(handles, labels, loc='best', ncol=3)
    r['magnetometer_randomwalk_correlation_time'] = [tau1, tau2, tau3]

    plt.figure()
    res1 = plot_allan_std_dev(df.t_sensor_combined_0__f_magnetometer_ga_0_, plot)
    handles, labels = plt.gca().get_legend_handles_labels()
    res2 = plot_allan_std_dev(df.t_sensor_combined_0__f_magnetometer_ga_1_, plot)
    res3 = plot_allan_std_dev(df.t_sensor_combined_0__f_magnetometer_ga_2_, plot)
    res = np.array([res1, res2, res3])
    plt.title('Allan variance plot - magnetometer')
    plt.legend(handles, labels, loc='best', ncol=3)
    for key in res1.keys():
        r['magnetometer_' + key] = [d[key] for d in [res1, res2, res3]]

    # baro
    plt.figure()
    tau = plot_autocorrelation(
        df.t_sensor_combined_0__f_baro_alt_meter,
        plot)
    plt.title('normalized autocorrelation - barometric altimeter')
    plt.legend(loc='best', ncol=3)
    r['baro_randomwalk_correlation_time'] = float(tau)

    plt.figure()
    res = plot_allan_std_dev(
        df.t_sensor_combined_0__f_baro_alt_meter,
        plot)
    plt.title('Allan variance plot - barometric altimeter')
    plt.legend(loc='best', ncol=3)
    for key in res1.keys():
        r['baro_' + key] = res[key]

    return r

def cached_log_processing(
        log, processing_func, msg_filter='',
        save_label='',
        force_processing=False, verbose=False):
    """
    Downsamples a log using mean aggregation and stores as a
    pkl for later loading.

    @param log: ulog to process
    @param processing_func: data = f(data0), how to process data
    @param msg_filter: filter to pass to ulog, '' is all topics
    @param save_label: label for processing pkl
    @param force_processing: force processing
    @param verbose: show status messages
    """
    #pylint: disable=too-many-arguments

    save_filename = log.replace('.ulg', '{:s}.pkl'.format(save_label))
    if not force_processing and os.path.exists(save_filename):
        if verbose:
            print('loading pickle', save_filename)
        with open(save_filename, 'rb') as f:
            d = pickle.load(f)
    else:
        if verbose:
            print('creating pickle', save_filename)
        d0 = read_ulog(log, msg_filter)
        d = processing_func(d0)
        with open(save_filename, 'wb') as f:
            pickle.dump(d, f)
    return d

#  vim: set et fenc=utf-8 ff=unix sts=0 sw=4 ts=4 :
