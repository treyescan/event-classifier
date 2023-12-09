# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the remodnavlad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
import numpy as np
from statsmodels.robust.scale import mad
from scipy import signal
from scipy import ndimage
from scipy.signal import savgol_filter
from scipy.ndimage import median_filter

from math import (
    degrees,
    atan2,
)

import logging
lgr = logging.getLogger('remodnav.clf')

## Physical setup
distance_to_screen = 65 # distance to screen in cm 
ppi = 94.34 # px per inch (monitor specification)
ppc = ppi/2.54 # px per cm
d = distance_to_screen * ppc # distance to screen in pixels

def find_peaks(vels, threshold):
    """Find above-threshold time periods

    Parameters
    ----------
    vels : array
      Velocities.
    threshold : float
      Velocity threshold.

    Returns
    -------
    list
      Each item is a tuple with start and end index of the window where
      velocities exceed the threshold.
    """
    def _get_vels(start, end):
        v = vels[start:end]
        v = v[~np.isnan(v)]
        return v

    sacs = []
    sac_on = None
    for i, v in enumerate(vels):
        if sac_on is None and v > threshold:
            # start of a saccade
            sac_on = i
        elif sac_on is not None and v < threshold:
            sacs.append([
                sac_on,
                i,
                _get_vels(
                    sac_on,
                    min(len(vels), i + 1))
            ])
            sac_on = None
    if sac_on:
        # end of data, but velocities still high
        sacs.append([
            sac_on,
            len(vels) - 1,
            _get_vels(sac_on, len(vels))])
    return sacs


def find_movement_onsetidx(vels, start_idx, sac_onset_velthresh):
    idx = start_idx
    while idx > 0 \
            and (vels[idx] > sac_onset_velthresh or
                 vels[idx] <= vels[idx - 1]):
        # find first local minimum after vel drops below onset threshold
        # going backwards in time

        # we used to do this, but it could mean detecting very long
        # saccades that consist of (mostly) missing data
        #         or np.isnan(vels[sacc_start])):
        idx -= 1
    return idx


def find_movement_offsetidx(vels, start_idx, off_velthresh):
    idx = start_idx
    # shift saccade end index to the first element that is below the
    # velocity threshold
    while idx < len(vels) - 1 \
            and (vels[idx] > off_velthresh or
                 (vels[idx] > vels[idx + 1])):
            # we used to do this, but it could mean detecting very long
            # saccades that consist of (mostly) missing data
            #    or np.isnan(vels[idx])):
        idx += 1
    return idx


def find_psoend(velocities, sac_velthresh, sac_peak_velthresh):
        pso_peaks = find_peaks(velocities, sac_peak_velthresh)
        if pso_peaks:
            pso_label = 'HPSO'
        else:
            pso_peaks = find_peaks(velocities, sac_velthresh)
            if pso_peaks:
                pso_label = 'LPSO'
        if not pso_peaks:
            # no PSO
            return

        # find minimum after the offset of the last reported peak
        pso_end = find_movement_offsetidx(
            velocities, pso_peaks[-1][1], sac_velthresh)

        if np.isnan(velocities[:pso_end]).sum():
            # we do not tolerate NaNs in PSO itervals
            return
        if pso_end > len(velocities):
            # velocities did not go down within the given window
            return

        return pso_label, pso_end


def filter_spikes(data):
    """In-place high-frequency spike filter

    Inspired by:

      Stampe, D. M. (1993). Heuristic filtering and reliable calibration
      methods for video-based pupil-tracking systems. Behavior Research
      Methods, Instruments, & Computers, 25(2), 137-142. doi:10.3758/bf03204486
    """
    def _filter(arr):
        # over all triples of neighboring samples
        for i in range(1, len(arr) - 1):
            if (arr[i - 1] < arr[i] and arr[i] > arr[i + 1]) \
                    or (arr[i - 1] > arr[i] and arr[i] < arr[i + 1]):
                # immediate sign-reversal of the difference from
                # x-1 -> x -> x+1
                prev_dist = abs(arr[i - 1] - arr[i])
                next_dist = abs(arr[i + 1] - arr[i])
                # replace x by the neighboring value that is closest
                # in value
                arr[i] = arr[i - 1] \
                    if prev_dist < next_dist else arr[i + 1]
        return arr

    data['x'] = _filter(data['x'])
    data['y'] = _filter(data['y'])
    return data


def get_dilated_nan_mask(arr, iterations, max_ignore_size=None):
    clusters, nclusters = ndimage.label(np.isnan(arr))
    # go through all clusters and remove any cluster that is less
    # the max_ignore_size
    for i in range(nclusters):
        # cluster index is base1
        i = i + 1
        if (clusters == i).sum() <= max_ignore_size:
            clusters[clusters == i] = 0
    # mask to cover all samples with dataloss > `max_ignore_size`
    mask = ndimage.binary_dilation(clusters > 0, iterations=iterations)
    return mask


def events2bids_events_tsv(events, fname, tsoffset=0.0):
    common_headers = [
        'label',
        'start_x', 'start_y', 'end_x', 'end_y',
        'amp',
        'peak_vel', 'med_vel', 'avg_vel',
        'start_time', 'end_time']
    with open(fname, 'w') as fp:
        fp.write('onset\tduration\t{}\n'.format(
            '\t'.join(common_headers)))
        for ev in sorted(events, key=lambda x: x['start_time']):
            fp.write('{:.3f}\t{:.3f}\t{}\n'.format(
                ev['start_time'] + tsoffset,
                ev['end_time'] - ev['start_time'],
                '\t'.join([
                    ('{}' if k == 'label'
                     else '{:.1f}' if k.endswith('_x') or k.endswith('_y')
                     else '{:.3f}').format(ev[k])
                    for k in common_headers
                ])))


def shift_elements(arr, num, fill_value):
    result = np.empty_like(arr)
    if num > 0:
        result[:num] = fill_value
        result[num:] = arr[:-num]
    elif num < 0:
        result[num:] = fill_value
        result[:num] = arr[-num:]
    else:
        result[:] = arr
    return result

class EyegazeClassifier(object):
    """Robust eye movement event detection in natural viewing conditions

    This algorithm is largely based on ideas taken from Nyström & Holmqvist
    (2010, https://doi.org/10.3758/BRM.42.1.188) and Friedman et al. (2018,
    https://doi.org/10.3758/s13428-018-1050-7), rearranged into a different
    algorithm flow to be able to work more robustly on data recorded under
    suboptimal conditions with dynamic stimuli (e.g. movies).
    """

    record_field_names = [
        'id', 'label',
        'start_time', 'end_time',
        'start_x', 'start_y',
        'end_x', 'end_y',
        'amp', 'peak_vel', 'med_vel', 'avg_vel',
    ]

    def __init__(self,
                 sampling_rate,
                 pursuit_velthresh=2.0,
                 noise_factor=5.0,
                 velthresh_startvelocity=300.0,
                 min_intersaccade_duration=0.04,
                 min_saccade_duration=0.01,
                 max_initial_saccade_freq=2.0,
                 saccade_context_window_length=1.0,
                 max_pso_duration=0.04,
                 min_fixation_duration=0.04,
                 min_pursuit_duration=0.04,
                 lowpass_cutoff_freq=4.0):
            self.sr = sr = sampling_rate
            self.velthresh_startvel = velthresh_startvelocity
            self.lp_cutoff_freq = lowpass_cutoff_freq
            self.pursuit_velthresh = pursuit_velthresh
            self.noise_factor = noise_factor

            for name, arg in [('min-intersaccade-duration',
                               min_intersaccade_duration),
                              ('min-saccade-duration', min_saccade_duration),
                              ('saccade-context-window-length',
                               saccade_context_window_length),
                              ('max-pso-duration', max_pso_duration),
                              ('min-fixation-duration', min_fixation_duration),
                              ('min-pursuit-duration', min_pursuit_duration)]:
                if arg * sr < 1:
                    lgr.warning(
                        " At the provided sampling rate of %s, the timeframe"
                        " for the parameter '%s' would be lower than a single"
                        " sample (%.1f samples). Consider increasing the"
                        " parameter value to prevent errors.", sr, name, arg*sr)
            # convert to #samples
            self.min_intersac_dur = int(
                min_intersaccade_duration * sr)
            self.min_sac_dur = int(
                min_saccade_duration * sr)
            self.sac_context_winlen = int(
                saccade_context_window_length * sr)
            self.max_pso_dur = int(
                max_pso_duration * sr)
            self.min_fix_dur = int(
                min_fixation_duration * sr)
            self.min_purs_dur = int(
                min_pursuit_duration * sr)

            self.max_sac_freq = max_initial_saccade_freq / sr

    def _get_signal_props(self, data):
        data = data[~np.isnan(data['vel'])]
        if not len(data):
            return np.nan, np.nan, np.nan, np.nan
        pv = data['vel'].max()
        amp = np.nan_to_num(np.rad2deg(np.arccos( 
            (data[0]['x'] * data[-1]['x'] + data[0]['y'] * data[-1]['y'] + d * d) /  \
                (
                    np.sqrt(data[0]['x'] ** 2 + data[0]['y'] ** 2 + d ** 2) * \
                    np.sqrt(data[-1]['x'] ** 2 + data[-1]['y'] ** 2 + d ** 2)
                )
        )))
        medvel = np.median(data['vel'])
        avgvel = np.mean(data['vel'])
        return amp, pv, medvel, avgvel

    def get_adaptive_saccade_velocity_velthresh(self, vels):
        """Determine saccade peak velocity threshold.

        Takes global noise-level of data into account. Implementation
        based on algorithm proposed by NYSTROM and HOLMQVIST (2010).

        Parameters
        ----------
        start : float
          Start velocity for adaptation algorithm. Should be larger than
          any conceivable minimal saccade velocity (in deg/s).
        TODO std unit multipliers

        Returns
        -------
        tuple
          (peak saccade velocity threshold, saccade onset velocity threshold).
          The latter (and lower) value can be used to determine a more precise
          saccade onset.
        """
        cur_thresh = self.velthresh_startvel

        def _get_thresh(cut):
            # helper function
            vel_uthr = vels[vels < cut]
            med = np.median(vel_uthr)
            scale = mad(vel_uthr)
            return med + 2 * self.noise_factor * scale, med, scale

        # re-compute threshold until value converges
        count = 0
        dif = 2
        while dif > 1 and count < 30:  # less than 1deg/s difference
            old_thresh = cur_thresh
            cur_thresh, med, scale = _get_thresh(old_thresh)
            if not cur_thresh:
                # safe-guard in case threshold runs to zero in
                # case of really clean and sparse data
                cur_thresh = old_thresh
                break
            lgr.debug(
                'Saccade threshold velocity: %.1f '
                '(non-saccade mvel: %.1f, stdvel: %.1f)',
                cur_thresh, med, scale)
            dif = abs(old_thresh - cur_thresh)
            count += 1

        return cur_thresh, (med + self.noise_factor * scale)

    def _mk_event_record(self, data, idx, label, start, end):
        return dict(zip(self.record_field_names, (
            idx,
            label,
            start,
            end,
            data[start]['x'],
            data[start]['y'],
            data[end - 1]['x'],
            data[end - 1]['y']) +
            self._get_signal_props(data[start:end])))

    def __call__(self, data, classify_isp=True, sort_events=True):
        # find threshold velocities
        sac_peak_med_velthresh, sac_onset_med_velthresh = \
            self.get_adaptive_saccade_velocity_velthresh(data['med_vel'])
        lgr.info(
            'Global saccade MEDIAN velocity thresholds: '
            '%.1f, %.1f (onset, peak)',
            sac_onset_med_velthresh, sac_peak_med_velthresh)

        saccade_locs = find_peaks(
            data['med_vel'],
            sac_peak_med_velthresh)

        events = []
        saccade_events = []
        for e in self._detect_saccades(
                saccade_locs,
                data,
                0,
                len(data),
                context=self.sac_context_winlen):
            saccade_events.append(e.copy())
            events.append(e)

        lgr.info('Start ISP classification')

        if classify_isp:
            events.extend(self._classify_intersaccade_periods(
                data,
                0,
                len(data),
                # needs to be in order of appearance
                sorted(saccade_events, key=lambda x: x['start_time']),
                saccade_detection=True))

        # make timing info absolute times, not samples
        for e in events:
            for i in ('start_time', 'end_time'):
                e[i] = e[i] / self.sr

        return sorted(events, key=lambda x: x['start_time']) \
            if sort_events else events

    def _detect_saccades(
            self,
            candidate_locs,
            data,
            start,
            end,
            context):

        saccade_events = []

        if context is None:
            # no context size was given, use all data
            # to determine velocity thresholds
            lgr.debug(
                'Determine velocity thresholds on full segment '
                '[%i, %i]', start, end)
            sac_peak_velthresh, sac_onset_velthresh = \
                self.get_adaptive_saccade_velocity_velthresh(
                    data['vel'][start:end])
            if candidate_locs is None:
                lgr.debug(
                    'Find velocity peaks on full segment '
                    '[%i, %i]', start, end)
                candidate_locs = [
                    (e[0] + start, e[1] + start, e[2]) for e in find_peaks(
                        data['vel'][start:end],
                        sac_peak_velthresh)]

        # status map indicating which event class any timepoint has been
        # assigned to so far
        status = np.zeros((len(data),), dtype=int)

        # loop over all peaks sorted by the sum of their velocities
        # i.e. longer and faster goes first
        for i, props in enumerate(sorted(
                candidate_locs, key=lambda x: x[2].sum(), reverse=True)):
            sacc_start, sacc_end, peakvels = props
            lgr.info(
                'Process peak velocity window [%i, %i] at ~%.1f deg/s',
                sacc_start, sacc_end, peakvels.mean())

            if context:
                # extract velocity data in the vicinity of the peak to
                # calibrate threshold
                win_start = max(
                    start,
                    sacc_start - int(context / 2))
                win_end = min(
                    end,
                    sacc_end + context - (sacc_start - win_start))
                lgr.debug(
                    'Determine velocity thresholds in context window '
                    '[%i, %i]', win_start, win_end)
                lgr.debug('Actual context window: [%i, %i] -> %i',
                          win_start, win_end, win_end - win_start)

                sac_peak_velthresh, sac_onset_velthresh = \
                    self.get_adaptive_saccade_velocity_velthresh(
                        data['vel'][win_start:win_end])

            lgr.info('Active saccade velocity thresholds: '
                     '%.1f, %.1f (onset, peak)',
                     sac_onset_velthresh, sac_peak_velthresh)

            # move backwards in time to find the saccade onset
            sacc_start = find_movement_onsetidx(
                data['vel'], sacc_start, sac_onset_velthresh)

            # move forward in time to find the saccade offset
            sacc_end = find_movement_offsetidx(
                data['vel'], sacc_end, sac_onset_velthresh)

            sacc_data = data[sacc_start:sacc_end]
            if sacc_end - sacc_start < self.min_sac_dur:
                lgr.debug('Skip saccade candidate, too short')
                continue
            elif np.sum(np.isnan(sacc_data['x'])):  # pragma: no cover
                # should not happen
                lgr.debug('Skip saccade candidate, missing data')
                continue
            elif status[
                    max(0,
                        sacc_start - self.min_intersac_dur):min(
                    len(data), sacc_end + self.min_intersac_dur)].sum():
                lgr.debug('Skip saccade candidate, too close to another event')
                continue

            lgr.debug('Found SACCADE [%i, %i]',
                      sacc_start, sacc_end)
            event = self._mk_event_record(data, i, "SACC", sacc_start, sacc_end)

            yield event.copy()
            saccade_events.append(event)

            # mark as a saccade
            status[sacc_start:sacc_end] = 1

            pso = find_psoend(
                data['vel'][sacc_end:sacc_end + self.max_pso_dur],
                sac_onset_velthresh,
                sac_peak_velthresh)
            if pso:
                pso_label, pso_end = pso
                lgr.debug('Found %s [%i, %i]',
                          pso_label, sacc_end, pso_end)
                psoevent = self._mk_event_record(
                    data, i, pso_label, sacc_end, sacc_end + pso_end)
                if psoevent['amp'] < saccade_events[-1]['amp']:
                    # discard PSO with amplitudes larger than their
                    # anchor saccades
                    yield psoevent.copy()
                    # mark as a saccade part
                    status[sacc_end:sacc_end + pso_end] = 1
                else:
                    lgr.debug(
                        'Ignore PSO, amplitude large than that of '
                        'the previous saccade: %.1f >= %.1f',
                        psoevent['amp'], saccade_events[-1]['amp'])

            if self.max_sac_freq and \
                    float(len(saccade_events)) / len(data) > self.max_sac_freq:
                lgr.info('Stop initial saccade detection, max frequency '
                         'reached')
                break

    def _classify_intersaccade_periods(
            self,
            data,
            start,
            end,
            saccade_events,
            saccade_detection):

        lgr.info(
            'Determine ISPs %i, %i (%i saccade-related events)',
            start, end, len(saccade_events))

        prev_sacc = None
        prev_pso = None
        for ev in saccade_events:
            if prev_sacc is None:
                if 'SAC' not in ev['label']:
                    continue
            elif prev_pso is None and 'PS' in ev['label']:
                prev_pso = ev
                continue
            elif 'SAC' not in ev['label']:
                continue

            # at this point we have a previous saccade (and possibly its PSO)
            # on record, and we have just found the next saccade
            # -> inter-saccade window is determined
            if prev_sacc is None:
                win_start = start
            else:
                if prev_pso is not None:
                    win_start = prev_pso['end_time']
                else:
                    win_start = prev_sacc['end_time']
            # enforce dtype for indexing
            win_end = ev['start_time']
            if win_start == win_end:
                prev_sacc = ev
                prev_pso = None
                continue

            lgr.info('Found ISP [%i:%i]', win_start, win_end)
            for e in self._classify_intersaccade_period(
                    data,
                    win_start,
                    win_end,
                    saccade_detection=saccade_detection):
                yield e

            # lastly, the current saccade becomes the previous one
            prev_sacc = ev
            prev_pso = None

        if prev_sacc is not None and prev_sacc['end_time'] == end:
            return

        lgr.debug("LAST_SEGMENT_ISP: %s -> %s", prev_sacc, prev_pso)
        # and for everything beyond the last saccade (if there was any)
        for e in self._classify_intersaccade_period(
                data,
                start if prev_sacc is None
                else prev_sacc['end_time'] if prev_pso is None
                else prev_pso['end_time'],
                end,
                saccade_detection=saccade_detection):
            yield e

    def _classify_intersaccade_period(
            self,
            data,
            start,
            end,
            saccade_detection):
        lgr.info('Determine NaN-free intervals in [%i:%i] (%i)',
                 start, end, end - start)

        # split the ISP up into its non-NaN pieces:
        win_start = None
        for idx in range(start, end + 1):
            if win_start is None and \
                    idx < len(data) and not np.isnan(data['x'][idx]):
                win_start = idx
            elif win_start is not None and \
                    ((idx == end) or np.isnan(data['x'][idx])):
                for e in self._classify_intersaccade_period_helper(
                        data,
                        win_start,
                        idx,
                        saccade_detection):
                    yield e
                # reset non-NaN window start
                win_start = None

    def _classify_intersaccade_period_helper(
            self,
            data,
            start,
            end,
            saccade_detection):
        # no NaN values in data at this point!
        lgr.info(
            'Process non-NaN segment [%i, %i] -> %i',
            start, end, end - start)

        label_remap = {
            'SACC': 'ISAC',
            'HPSO': 'IHPS',
            'LPSO': 'ILPS',
        }

        length = end - start
        # detect saccades, if the there is enough space to maintain minimal
        # distance to other saccades
        if length > (
                2 * self.min_intersac_dur) \
                + self.min_sac_dur + self.max_pso_dur:
            lgr.info('Perform saccade detection in [%i:%i]', start, end)
            saccades = self._detect_saccades(
                None,
                data,
                start,
                end,
                context=None)
            saccade_events = []
            if saccades is not None:
                kill_pso = False
                for s in saccades:
                    if kill_pso:
                        kill_pso = False
                        if s['label'].endswith('PSO'):
                            continue
                    if s['start_time'] - start < self.min_intersac_dur or \
                            end - s['end_time'] < self.min_intersac_dur:
                        # to close to another saccade
                        kill_pso = True
                        continue
                    s['label'] = label_remap.get(s['label'], s['label'])
                    # need to make a copy of the dict to not have outside
                    # modification interfere with further inside processing
                    yield s.copy()
                    saccade_events.append(s)
            if saccade_events:
                lgr.info('Found additional saccades in ISP')
                # and now process the intervals between the saccades
                for e in self._classify_intersaccade_periods(
                        data,
                        start,
                        end,
                        sorted(saccade_events,
                               key=lambda x: x['start_time']),
                        saccade_detection=False):
                    yield e
                return

        # what is this time between two saccades?
        for e in self._fix_or_pursuit(data, start, end):
            yield e

    def _fix_or_pursuit(self, data, start, end):
        if end - start < self.min_fix_dur:
            return
        # we have at least enough data for a really short fixation
        win_data = data[start:end].copy()

        # heavy smoothing of the time series, whatever this non-saccade
        # interval is, the key info should be in its low-freq components
        def _butter_lowpass(cutoff, fs, order=5):
            nyq = 0.5 * fs
            normal_cutoff = cutoff / nyq
            b, a = signal.butter(
                order,
                normal_cutoff,
                btype='low',
                analog=False)
            return b, a

        b, a = _butter_lowpass(self.lp_cutoff_freq, self.sr)
        win_data['x'] = signal.filtfilt(b, a, win_data['x'], method='gust')
        win_data['y'] = signal.filtfilt(b, a, win_data['y'], method='gust')
        # no entry for first datapoint!
        win_vels = self._get_velocities(win_data)

        pursuit_peaks = find_peaks(win_vels, self.pursuit_velthresh)

        # detect rest is very similar in logic to _detect_saccades()

        # status map indicating which event class any timepoint has been
        # assigned to so far, zero is fixation
        pursuit_tps = np.zeros((len(win_vels),), dtype=int)

        # loop over all peaks sorted by the sum of their velocities
        # i.e. longer and faster goes first
        for i, props in enumerate(sorted(
                pursuit_peaks, key=lambda x: x[2].sum(), reverse=True)):
            pursuit_start, pursuit_end, peakvels = props
            lgr.debug(
                'Process pursuit peak velocity window [%i, %i] at ~%.1f deg/s',
                start + pursuit_start, start + pursuit_end, peakvels.mean())

            # move backwards in time to find the pursuit onset
            pursuit_start = find_movement_onsetidx(
                win_vels, pursuit_start, self.pursuit_velthresh)

            # move forward in time to find the pursuit offset
            pursuit_end = find_movement_offsetidx(
                win_vels, pursuit_end, self.pursuit_velthresh)

            if pursuit_end - pursuit_start < self.min_purs_dur:
                lgr.debug('Skip pursuit candidate, too short')
                continue

            # mark as a pursuit event
            pursuit_tps[pursuit_start:pursuit_end] = 1

        evs = []
        for i, tp in enumerate(pursuit_tps):
            if not evs:
                # first event info
                evs.append([tp, i, i])
            elif evs[-1][0] == tp:
                # more of the same type of event, extend existing record
                evs[-1][-1] = i
            else:
                evs.append([tp, i, i])
        # take out all the evs that are too short
        evs = [ev for ev in evs
               if ev[2] - ev[1] >= {
                   1: self.min_purs_dur,
                   0: self.min_fix_dur}[ev[0]]]
        merged_evs = []
        for i, ev in enumerate(evs):
            if i == len(evs) - 1:
                merged_evs.append(ev)
                break
            if ev[0] == evs[i + 1][0]:
                # same type as coming event, merge and ignore this one
                evs[i + 1][1] = ev[1]
                continue
            else:
                # make boundary in the middle
                boundary = ev[2] + int((evs[i + 1][1] - ev[2]) / 2)
                ev[2] = boundary
                evs[i + 1][1] = boundary
                merged_evs.append(ev)
        if not merged_evs:
            # if we found nothing, this is all a fixation
            merged_evs.append([0, 0, len(win_data)])
        else:
            # compensate for tiny snips at start and end
            merged_evs[0][1] = 0
            merged_evs[-1][2] = len(win_data)

        # submit
        for ev in merged_evs:
            label = 'PURS' if ev[0] else 'FIXA'
            # +1 to compensate for the shift in the velocity
            # vector index
            estart = start + ev[1]
            eend = start + ev[-1]
            lgr.debug('Found %s [%i, %i]',
                      label, estart, eend)

            # change of events or end
            yield self._mk_event_record(
                data,
                None,
                label,
                estart,
                eend)

    def _get_velocities(self, original_data):

        # Create a local data array with previous x/y (shifted)
        data = np.zeros(original_data.shape, dtype=[
            ('x', '<f8'), ('y', '<f8'), ('z', '<f8'), 
            ('prev_x', '<f8'), ('prev_y', '<f8'), ('prev_z', '<f8'),
            ('denominator', '<f8'), ('divisor', '<f8'), ('phi', '<f8'),
            ('velocity', '<f8')
        ])
        data['x'] = original_data['x']
        data['y'] = original_data['y']
        data['z'] = d
        data['prev_x'] = shift_elements(original_data['x'], 1, np.nan)
        data['prev_y'] = shift_elements(original_data['y'], 1, np.nan)
        data['prev_z'] = d

        # Calculate the angle (phi) by using: cos 𝜙 = (a⋅b) / (|a||b|)
        data['denominator'] = (data['x'] * data['prev_x']) + (data['y'] * data['prev_y']) + (data['z'] * data['prev_z'])
        data['divisor'] = np.sqrt(data['x'] ** 2 + data['y'] ** 2 + data['z'] ** 2) * np.sqrt(data['prev_x'] ** 2 + data['prev_y'] ** 2 + data['prev_z'] ** 2)
        data['phi'] = np.nan_to_num(np.rad2deg(np.arccos(data['denominator'] / data['divisor'])))

        # Calculate the velocity (deg/s) based on the angle
        data['velocity'] = data['phi'] / (1/self.sr)

        # Only return the velocities, make sure to remove the last row since we shifted down
        velocities = data['velocity'][1:]
        return velocities

    def preproc(
            self,
            data,
            min_blink_duration=0.02,
            dilate_nan=0.01,
            median_filter_length=0.05, 
            savgol_length=0.019,
            savgol_polyord=2,
            max_vel=1000.0):
        """
        Parameters
        ----------
        min_blink_duration : float
          In seconds. Any signal loss shorter than this duration will not be
          considered for `dilate_nan`.
        dilate_nan : float
          Duration by which to dilate a blink window (missing data segment) on
          either side (in seconds).
        median_filter_length : float
          Filter window length in seconds.
        savgol_length : float
          Filter window length in seconds.
        savgol_polyord : int
          Filter polynomial order used to fit the samples.
        max_vel : float
          Maximum velocity in deg/s. Any velocity value larger than this
          threshold will be replaced by the previous velocity value.
          Additionally a warning will be issued to indicate a potentially
          inappropriate filter setup.
        """
        # convert params in seconds to #samples
        dilate_nan = int(dilate_nan * self.sr)
        min_blink_duration = int(min_blink_duration * self.sr)
        # sanity check window length - it needs to be odd, and greater than the
        # polynomial order of the Savitzgy-Golay filter
        if (int(savgol_length * self.sr) % 2 != 1 or
            int(savgol_length * self.sr) < savgol_polyord) and \
                savgol_length != 0.0:
            raise ValueError("\n"\
                "Inappropriate window size for Savitzgy-Golay "\
                "filter. Please adjust --savgol-length such that the "\
                "formula 'savgol-length x sampling rate' results in a "\
                "number that can be rounded down to an odd integer that "\
                "is higher than {}. Currently, --savgol-length is {} and "\
                "the sampling rate is {} "\
                "which results in {}.".format(savgol_polyord,
                                              savgol_length,
                                              self.sr,
                                              int(savgol_length * self.sr)))
        savgol_length = int(savgol_length * self.sr)
        median_filter_length = int(median_filter_length * self.sr)
        # in-place spike filter
        data = filter_spikes(data)

        # for signal loss exceeding the minimum blink duration, add additional
        # dilate_nan at either end
        # find clusters of "no data"
        if dilate_nan:
            lgr.info('Dilate NaN segments by %i samples', dilate_nan)
            mask = get_dilated_nan_mask(
                data['x'],
                dilate_nan,
                min_blink_duration)
            data['x'][mask] = np.nan
            data['y'][mask] = np.nan

        if savgol_length:
            lgr.info(
                'Smooth coordinates with Savitzy-Golay filter (len=%i, ord=%i)',
                savgol_length, savgol_polyord)
            for i in ('x', 'y'):
                data[i] = savgol_filter(data[i], savgol_length, savgol_polyord)

        # velocity calculation, exclude velocities over `max_vel`
        # no entry for first datapoint!
        velocities = self._get_velocities(data)

        if median_filter_length:
            lgr.info(
                'Add velocities computed from median-filtered (len=%i) '
                'coordinates', median_filter_length)
            med_velocities = np.zeros((len(data),), velocities.dtype)
            median_filtered_data = data.copy()
            median_filtered_data['x'] = median_filter(data['x'], size=median_filter_length)
            median_filtered_data['y'] = median_filter(data['y'], size=median_filter_length)
            med_velocities[1:] = self._get_velocities(median_filtered_data)
            
            # remove any velocity bordering NaN
            med_velocities[get_dilated_nan_mask(
                med_velocities, dilate_nan, 0)] = np.nan

        # replace "too fast" velocities with previous velocity
        # add missing first datapoint
        filtered_velocities = [float(0)]
        for vel in velocities:
            if vel > max_vel:  # deg/s
                # ignore very fast velocities
                lgr.warning(
                    'Computed velocity exceeds threshold. '
                    'Inappropriate filter setup? [%.1f > %.1f deg/s]',
                    vel,
                    max_vel)
                vel = filtered_velocities[-1]
            filtered_velocities.append(vel)
        velocities = np.array(filtered_velocities)
        if not median_filter_length:
            # no median filtering, but we need the field in our dict later,
            # so we just reuse the original velocities
            med_velocities = velocities
        # acceleration is change of velocities over the last time unit
        acceleration = np.zeros(velocities.shape, velocities.dtype)
        acceleration[1:] = (velocities[1:] - velocities[:-1]) * self.sr

        arrs = [med_velocities]
        names = ['med_vel']
        arrs.extend([
            velocities,
            acceleration,
            data['x'],
            data['y']])
        names.extend(['vel', 'accel', 'x', 'y'])
        return np.core.records.fromarrays(arrs, names=names)

    def show_gaze(self, data=None, pp=None, events=None, show_vels=True):
        pp['vel'] = pp['vel'] * 2
        
        colors = {
            'FIXA': 'xkcd:beige',
            'PURS': 'xkcd:burnt sienna',
            'SACC': 'xkcd:spring green',
            'ISAC': 'xkcd:pea green',
            'HPSO': 'xkcd:azure',
            'IHPS': 'xkcd:azure',
            'LPSO': 'xkcd:faded blue',
            'ILPS': 'xkcd:faded blue',
        }

        import pylab as pl
        if events is not None:
            for ev in events:
                pl.axvspan(
                    ev['start_time'],
                    ev['end_time'],
                    color=colors[ev['label']],
                    alpha=0.8)
        ntimepoints = len(pp) if pp is not None else len(data)
        timepoints = np.linspace(0, ntimepoints / self.sr, ntimepoints)
        if data is not None:
            pl.plot(
                timepoints,
                data['x'],
                color='xkcd:pig pink', lw=1)
            pl.plot(
                timepoints,
                data['y'],
                color='xkcd:pig pink', lw=1)
        if pp is not None:

            pl.plot(
                timepoints,
                pp['x'],
                color='purple', lw=1)
            pl.plot(
                timepoints,
                pp['y'],
                color='blue', lw=1)
            if show_vels:
                pl.plot(
                    timepoints,
                    pp['vel'],
                    color='red', lw=1)