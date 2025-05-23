#!/usr/bin/env python3
"""
Graphical interface to view data sets
Part of Ephysanalysis package
"""

import importlib
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from pylibrary.tools import cprint as CP
from pylibrary.tools import fileselector as FS
from pyqtgraph.parametertree import Parameter, ParameterTree

import ephys.tools.minicalcs as minicalcs

from ephys.datareaders import acq4_reader
from ephys.ephys_analysis import rm_tau_analysis, spike_analysis
from ephys.mini_analyses import minis_methods, minis_methods_common
import ephys.mini_analyses.mini_event_dataclasses as MEDC  # get result datastructure

from ephys.tools import digital_filters
from ephys.tools import functions as FN


all_modules = [
    acq4_reader,
    spike_analysis,
    rm_tau_analysis,
    digital_filters,
    minis_methods,
    minis_methods_common,
    minicalcs,
    MEDC,
    FN,
]


class MiniViewer(pg.QtWidgets.QWidget):
    keyPressed = pg.QtCore.pyqtSignal(pg.QtCore.QEvent)

    def __init__(self, app=None):
        super(MiniViewer, self).__init__()
        self.app = app
        self.verbose = False
        self.settings = pg.QtCore.QSettings("ManisLab", "MiniViewer")
        self.recent_files = {"Previous": [], "MostRecent": []}
        self.recent_files_filename = "mini_viewer_recent_files.cfg"
        if Path(self.recent_files_filename).is_file():
            self.recent_files = pg.configfile.readConfigFile(self.recent_files_filename)
            self.settings.setValue("recent_files", self.recent_files["Previous"])
        else:  # create empty recent_files file
            pg.configfile.writeConfigFile(self.recent_files, self.recent_files_filename)
        self.datadir = "/Volumes/Pegasus_002/ManisLab_Data3/Kasten_Michael"
        self.AR = (
            acq4_reader.acq4_reader()
        )  # make our own private cersion of the analysis and reader
        self.SP = spike_analysis.SpikeAnalysis()
        self.RM = rm_tau_analysis.RmTauAnalysis()
        self.ampdataname = "MultiClamp1.ma"

        self.tb = None
        self.notch_60HzHarmonics = np.arange(60.0, 4000.0, 60.0)
        self.notch_60HzHarmonics_4K = [
            60.0,
            120.0,
            180.0,
            240.0,
            300.0,
            360.0,
            420.0,
            480.02,
            660.0,
            720.2,
            780.0,
            900.0,
            960.4,
            1020.03,
            1140.04,
            1260.5,
            1380.5,
            1500.6,
            1620.6,
            1740.6,
            1860.6,
            1980.6,
            2100.8,
            2220.8,
            2340.8,
            2460.8,
            2581.0,
            2701.0,
            2821.0,
            2941.0,
            3061.2,
            4000.0,
        ]

        self.filters = MEDC.Filtering()  # create filter class
        # modify some defaults
        self.filters.Notch_frequencies = None
        self.filters.Notch_Q = 90.0
        self.filters.HPF_frequency = None
        self.filters.LPF_frequency = 2500.0
        self.filters.enabled = True

        self.curves = []
        self.crits = []
        self.scatter = []
        self.threshold_line = None
        self.lines = []
        self.fitlines = []
        self.tstart = 0.1
        self.tend = 0.0
        self.maxT = 0.6
        self.default_tau1 = 0.001
        self.default_tau2 = 0.004
        self.tau1 = 0.001  # value in the spinbox for template
        self.tau2 = 0.004  # value in the spinbox
        self.minis_risetau = self.tau1  # will be value returned from analysis
        self.minis_falltau = self.tau2
        self.risepower = 2
        self.event_post_time = 0.015
        self.method = None
        self.Order = 7
        self.pars = MEDC.AnalysisPars()
        self.pars.risepower = self.risepower

        self.thresh_reSD = 3.0
        self.ZC_mindur = 1e-3  # sec
        self.ZC_minPeak = 5e-12  # A
        self.sign = -1
        self.minis_sign = "-"
        self.scalar = 1
        self.n_adjusted = 0
        self.curve_set = False
        self.last_method = "AJ"
        self.compare_flag = False
        self.compare_data = None
        self.data_set = None
        currentpath = Path.cwd()
        self.filelistpath = Path(currentpath, "ephys/tools/data/files.toml")
        self.maxPreviousFiles = 10  # limit of # of files held in history of filenames
        self.MINC = minicalcs.MiniCalcs(parent=self)
        self.MA = None
        self.method_update = {
            "CB": self.MINC.CB_update,
            "AJ": self.MINC.AJ_update,
            "ZC": self.MINC.ZC_update,
            "RS": self.MINC.RS_update,
        }
        self.method_mapper = {
            "CB": self.MINC.CB,
            "AJ": self.MINC.AJ,
            "ZC": self.MINC.ZC,
            "RS": self.MINC.RS,
        }

    def getProtocolDir(self, reload_last=False):
        current_filename = None
        sel = None
        if not reload_last:
            sel = FS.FileSelector(dialogtype="dir", startingdir=self.datadir)
            current_filename = sel.fileName
        else:
            self.recent_files = {}
            self.recent_files = pg.configfile.readConfigFile(self.recent_files_filename)
            if len(self.recent_files["MostRecent"]) > 0:
                current_filename = self.recent_files["MostRecent"][0]
            if current_filename is None:
                print("No recent files found")
            else:
                sel = current_filename
        if sel is None:
            return
        self.clampfiles = []
        self.AR.setDataName(self.ampdataname)
        if current_filename is not None:
            self.pdirs = Path(current_filename).glob(f"**/{self.ampdataname:s}")
            for p in self.pdirs:
                self.clampfiles.append(p)
                # print(p)
            wtparts = Path(current_filename).parts
            wt = "/".join(wtparts[-4:])
        else:
            wt = "No File"
        self.fileName = current_filename
        self.win.setWindowTitle(wt)
        self.w1.slider.setValue(0)
        print("# clamp files (traces): ", len(self.clampfiles))
        self.w1.slider.setRange(0, len(self.clampfiles) - 1)
        self.w1.slider.setTickInterval(10)
        self.protocolPath = self.fileName
        self.compare_data = False  # new prototocol; trigger new comparision if needed
        if self.recent_files == {}:
            # first attempt to read the current recent files file
            self.recent_files = {"Previous": [str(self.fileName)], "MostRecent": [str(self.fileName)]}
        else:
            if self.fileName not in self.recent_files["Previous"]:
                self.recent_files["Previous"].insert(0, str(self.fileName))
            self.recent_files["Previous"] = self.recent_files["Previous"][: self.maxPreviousFiles]
        pg.configfile.writeConfigFile(self.recent_files, self.recent_files_filename)
        self.settings.setValue("recent_files", self.recent_files["Previous"])

        self.load_data()

    def setProtocol(self, date, sliceno, cellno, protocolName):
        # create an IV protocol path:
        self.newbr = 0.0
        self.protocolBridge = 0.0
        self.date = date
        self.slice = sliceno
        self.cell = cellno
        if date.find("_") < 0:
            self.date = date + "_000"
        if isinstance(sliceno, int):
            self.slice = "slice_{0:03d}".format(sliceno)
        if isinstance(cellno, int):
            self.cell = "cell_{0:03d}".format(cellno)
        self.protocolName = protocolName
        self.protocolPath = Path(self.datadir, self.date, self.slice, self.cell, self.protocolName)
        self.protocolKey = Path(self.date, self.slice, self.cell, self.protocolName)
        if not self.protocolPath.is_dir():
            print("dir not found: ", str(self.protocolPath))
            return

    def load_data(self):
        self.AR.setProtocol(self.protocolPath)  # define the protocol path where the data is
        print("Loading data from: ", self.protocolPath)
        # self.info = self.AR.getDataInfo(Path(mapdir))  # copy out the info
        self.MA = minis_methods.MiniAnalyses()  # get a minianalysis instance
        if self.AR.getData(silent=False):  # get that data.
            self.filters_applied = False
            # trim time window if needed
            dt = 1.0 / self.AR.sample_rate[0]
            # trx = self.AR.data_array
            if self.tend == 0:
                tend = self.AR.data_array.shape[1] * dt
            else:
                tend = self.tend
            istart = int(self.tstart / dt)
            iend = int(tend / dt)
            self.AR.data_array = self.AR.data_array[:, istart:iend]
            self.mod_data = self.AR.data_array.copy()
            self.trace_end_index = self.mod_data.shape[1]
            self.maxT = self.AR.sample_rate[0] * self.trace_end_index
            self.w1.slider.setValue(0)
            # load depends on the analysis...

            self.MA.setup(
                datasource="MiniAnalyses",
                ntraces=self.mod_data.shape[0],
                tau1=self.tau1,
                tau2=self.tau2,
                dt_seconds=self.AR.sample_interval,
                template_tmax=0.05,  # sec
                template_pre_time=0.001,  # sec
                event_post_time=self.event_post_time,
                sign=self.sign,
                risepower=self.risepower,
                threshold=self.thresh_reSD,
                filters=self.filters,
            )
            self.MA.set_timebase(self.AR.time_base)
            self.MA.verbose = self.verbose
            if self.verbose:
                print("after setup, filters: ", self.MA.filters)
            self.apply_filtering()
            if self.verbose:
                print("after filter application: ", self.MA.filters)
            self.update_traces()
        else:
            print("Data not loaded")

    def apply_filtering(self):
        """Apply filtering all at once to all traxes upon reading"""

        if self.filters_applied:
            print("Filtering already applied")
            return
        if not self.filters.enabled:
            return
        self.MA.set_dt_seconds(self.AR.sample_interval)

        print("Preparing data...")
        if self.verbose:
            print(self.filters)
        self.MA.prepare_data(data=self.mod_data, pars=self.pars)
        if self.verbose:
            print("data prepared ", self.MA.data_prepared)
        self.mod_data = self.MA.data
        itrace = self.mod_data.shape[0]
        # for itrace in range(self.mod_data.shape[0]):
        #     self.mod_data[itrace] = FN.adaptiveDetrend(
        #         self.mod_data[itrace], x=self.AR.time_base[:self.trace_end_index], threshold=3.0
        #     )

        #     if self.notch_frequency != "None":
        #         if self.notch_frequency == "60HzHarm":
        #             notchfreqs = self.notch_60HzHarmonics
        #         elif self.notch_frequency == "60HzHarm+4K":
        #             notchfreqs = self.notch_60HzHarmonics_4K
        #         else:
        #             notchfreqs = [self.notch_frequency]
        #         if itrace == 0:
        #             CP.cprint("y", f"Notch Filtering trace{itrace:d}")
        #         self.mod_data[itrace] = digital_filters.NotchFilterComb(
        #             self.mod_data[itrace],
        #             notchf=notchfreqs,
        #             Q=self.notch_Q,
        #             QScale=False,
        #             samplefreq=self.AR.sample_rate[0],
        #         )
        #     if self.LPF != "None":
        #         if itrace == 0:
        #             CP.cprint("y", f"LPF Filtering at: {self.LPF:.2f} trace{itrace:d}")
        #         #            self.mod_data[self.current_trace]  = digital_filters.SignalFilter_LPFBessel(
        #         self.mod_data[itrace] = digital_filters.SignalFilter_SOS(
        #             self.mod_data[itrace],
        #             self.LPF,
        #             samplefreq=self.AR.sample_rate[0],
        #             NPole=16,
        #         )
        #     # self.mod_data = digital_filters.SignalFilter_LPFBessel(
        #     #         self.mod_data, self.HPF, samplefreq=self.AR.sample_rate[0], filtertype="high", NPole=8
        #     #     )
        CP.cprint("y", f"Applied filtering to {itrace:d} traces")
        self.filters_applied = True

    def _getpars(self):
        signdict = {"-": -1, "+": 1}
        # self.tau1 = 1e-3 * self.minis_risetau  # .value()*1e-3
        # self.tau2 = 1e-3 * self.minis_falltau  # .value()*1e-3
        sign = self.minis_sign
        self.sign = signdict[sign]
        # print(self.tau1, self.tau2, self.thresh, self.sign)

    def update_threshold(self):
        self.threshold_line.setPos(self.thresh_reSD)

        self.method_update[self.last_method]()  # threshold/scroll, just update

    def update_traces(self, trace: int = None):

        if len(self.AR.traces) == 0:
            return
        if trace is None:
            self.current_trace = int(self.w1.x)
        else:
            self.current_trace = trace
        self.dataplot.setTitle(f"Trace: {self.current_trace:d}")
        for c in self.curves:
            c.clear()
        for s in self.scatter:
            s.clear()
        for line in self.lines:
            self.dataplot.removeItem(line)
        self.clear_fit_lines()
        self.scatter = []
        self.curves = []
        self.lines = []
        self.curve_set = False
        if self.current_trace >= np.array(self.AR.data_array).shape[0]:
            self.dataplot.setTitle(f"Trace > Max traces: {np.array(self.AR.data_array).shape[0]:d}")
            return
        
        self.curves.append(
            self.dataplot.plot(
                self.AR.time_base[: self.trace_end_index],
                self.mod_data[self.current_trace][: self.trace_end_index],
                pen=pg.intColor(1),
            )
        )
        self.current_data = self.mod_data[self.current_trace]
        self.tb = self.AR.time_base[: self.trace_end_index]
        self.curve_set = True
        if self.method is not None:
            self.MINC.decorate(self.method)
        return

    def update_analysis(self):
        print("self.method: ", self.method)
        self.risepower = 4
        self.MA.set_filters(self.filters)
        self.MINC = minicalcs.MiniCalcs(parent=self)

        self.method_mapper[self.last_method]()  # recompute from scratch
        if self.method is not None:
            self.MINC.decorate(self.method)
        self.MINC.show_fitting_pars()
        # self.compareEvents()

    def quit(self):
        exit(0)

    def keyPressEvent(self, event):
        super(MiniViewer, self).keyPressEvent(event)
        print("key pressed, event=", event)
        self.keyPressed.emit(event)

    def on_key(self, event):
        print("Got event key: ", event.key())
        if event.key() == pg.Qt.Key_Right and self.slider_value < len(self.clampfiles):
            self.w1.slider.setValue(self.slider.value() + 1)
        elif event.key() == pg.Qt.Key_Left and self.slider_value() > 0:
            self.w1.slider.setValue(self.slider.value() - 1)
        else:
            pg.QtGui.QWidget.keyPressEvent(self, event)  # just pass it on

    def getProtocols(self):
        thisdata = self.df.index[
            (self.df["date"] == self.date)
            & (self.df["slice_slice"] == self.slice)
            & (self.df["cell_cell"] == self.cell)
        ].tolist()
        if len(thisdata) > 1:
            raise ValueError("Search for data resulted in more than one entry!")
        ivprots = self.df.iloc[thisdata]["IV"].values[0]  # all the protocols in the dict
        return thisdata, ivprots

    def getProtocol(self, protocolName):
        thisdata, ivprots = self.getIVProtocols()
        if protocolName not in ivprots.keys():
            return None
        else:
            return ivprots[protocolName]

    def compareEvents(self):
        """
        Try to compare traces from what is shown with the events file on the disk
        """
        if not self.compare_flag:
            if len(self.lines) > 0:
                for line in self.lines:
                    self.dataplot.removeItem(line)
            self.compare_flag = False
            self.compare_data = None
            self.data_set = None
            return

        if self.compare_data is None:
            pathparts = Path(self.fileName).parts
            evfolder = Path("datasets", "NF107Ai32_Het", "events")
            evfile = pathparts[-4] + "~" + pathparts[-3] + "~" + pathparts[-2] + ".pkl"
            evfile = Path(evfolder, evfile)
            wtparts = Path(self.fileName).parts
            self.data_set = Path("/".join(wtparts[-4:]))
            # proto = wtparts[-1]
            if not evfile.is_file():
                print("Evfile: ", evfile, " is not a file?")
                self.compare_data = False  # no comparison file; just return
                self.compare_d = None
                return
            with open(evfile, "rb") as fh:
                self.compare_data = pickle.load(fh)
        if self.compare_data is not None:
            rate = self.compare_data[self.data_set]["rate"]
            ev = self.compare_data[self.data_set]["events"]  # list of trials, spots
            tr = self.current_trace  # which spot/trace?
            trd = ev[0][tr]  # get the trace data
            for line in np.array(trd["peaktimes"][0]) * rate:
                self.lines.append(pg.InfiniteLine(line, pen="m"))
                self.dataplot.addItem(self.lines[-1])
            self.scatter.append(
                self.dataplot.plot(
                    np.array(trd["peaktimes"][0]) * rate,
                    trd["smpks"][0],
                    pen=None,
                    symbol="t",
                    symbolPen=None,
                    symbolSize=12,
                    symbolBrush=(0, 255, 0, 255),
                )
            )

    def show_data_pars(self):
        if self.compare_flag and self.compare_data is not None:
            CP.cprint("g", "Parameters for current dataset: ")
            if "analysis_parameters" in list(self.compare_data[self.data_set].keys()):
                print(self.compare_data[self.data_set]["analysis_parameters"])
            else:
                print(
                    "analysis pars not in dateset: ",
                    self.compare_data[self.data_set].keys(),
                )

    def clear_fit_lines(self):
        if len(self.fitlines) > 0:
            for l in self.fitlines:
                self.fitplot.removeItem(l)
            self.fitlines = []

    def copy_fits(self):
        if not self.method.summary.average.averaged:
            CP.cprint("r", "Fit not yet run")
            return
        self.minis_risetau = self.method.summary.average.fitted_tau1
        self.minis_falltau = self.method.summary.average.fitted_tau2

    def write_dataset(self):
        pass

    def build_ptree(self):
        self.params = [
            # {"name": "Pick Cell", "type": "list", "values": cellvalues, "value": cellvalues[0]},
            {
                "name": "PreProcessing",
                "type": "group",
                "children": [
                    {
                        "name": "Channel Name",
                        "type": "list",
                        "limits": [
                            "Clamp1.ma",
                            "MultiClamp1.ma",
                            "Clamp2.ma",
                            "MultiClamp2.ma",
                        ],
                        "value": "MultiClamp1.ma",
                    },
                    {
                        "name": "Set Start (s)",
                        "type": "float",
                        "value": 0.1,
                        "limits": (0, 30.0),
                        "default": 0.0,
                    },
                    {
                        "name": "Set End (s)",
                        "type": "float",
                        "value": 0.0,
                        "limits": (0, 30.0),
                        "default": 0.0,
                    },
                    {
                        "name": "Enable Filtering",
                        "type": "bool",
                        "value": True,
                        "default": True,
                    },
                    {
                        "name": "Detrend Method",
                        "type": "list",
                        "limits": ["None", "meegkit", "scipy"],
                        "default": "meegkit",
                    },
                    {
                        "name": "LPF",
                        "type": "list",
                        "limits": [
                            "None",
                            500.0,
                            1000.0,
                            1200.0,
                            1500.0,
                            1800.0,
                            2000.0,
                            2500.0,
                            3000.0,
                            4000.0,
                            5000.0,
                        ],
                        "value": self.filters.LPF_frequency,
                        "default": self.filters.LPF_frequency,
                        "renamable": True,
                    },
                    {
                        "name": "HPF",
                        "type": "list",
                        "limits": [
                            "None",
                            0.1,
                            0.5,
                            1.0,
                            2.0,
                            5.0,
                            10.0,
                        ],
                        "value": self.filters.HPF_frequency,
                        "default": self.filters.HPF_frequency,
                        "renamable": True,
                    },
                    {
                        "name": "Notch Frequency",
                        "type": "list",
                        "limits": [
                            "None",
                            "60HzHarm",
                            "60HzHarm+4K",
                            30.0,
                            60.0,
                            120.0,
                            180.0,
                            240.0,
                        ],
                        "value": self.filters.Notch_frequencies,
                    },
                    {
                        "name": "Notch Q",
                        "type": "float",
                        "value": self.filters.Notch_Q,
                        "limits": (1, 300.0),
                        "default": 60.0,
                    },
                ],
            },  # end group
            # {"name": "Apply Filters", "type": "action"},
            {"name": "Get Protocol", "type": "action"},
            {"name": "Reload Last Protocol", "type": "action"},
            {
                "name": "Mini Analysis",
                "type": "group",
                "children": [
                    {
                        "name": "Method",
                        "type": "list",
                        "limits": ["AJ", "CB", "RS", "ZC"],
                        "value": "AJ",
                    },
                    {
                        "name": "Sign",
                        "type": "list",
                        "limits": ["+", "-"],
                        "value": "-",
                    },
                    {
                        "name": "Rise Tau",
                        "type": "float",
                        "value": self.default_tau1,
                        "step": 0.0001,
                        "limits": (0.0001, 0.100),
                        "default": self.default_tau1,
                        "units": "s",
                    },
                    {
                        "name": "Fall Tau",
                        "type": "float",
                        "value": self.default_tau2,
                        "step": 0.0005,
                        "limits": (0.001, 1.00),
                        "default": self.default_tau2,
                        "units": "s",
                    },
                    {
                        "name": "Threshold",
                        "type": "float",
                        "value": 3.0,
                        "step": 0.1,
                        "limits": (-1e-6, 50.0),
                        "default": 2.5,
                    },
                    {
                        "name": "Order",
                        "type": "float",
                        "value": 7,
                        "step": 1,
                        "limits": (1, 100),
                        "default": 7,
                    },
                    {"name": "Analyze Events", "type": "action"},
                ],
            },
            {
                "name": "Compare Events",
                "type": "bool",
                "value": False,
                "tip": "Try to compare with events previously analyzed",
            },
            {"name": "Verbose", "type": "bool", "value": False, "default": False},
            {"name": "Show Fitting Pars", "type": "action"},
            {"name": "Copy Fit to template", "type": "action"},
            {"name": "Write Dataset text", "type": "action"},
            {"name": "Reload", "type": "action"},
            {"name": "Quit", "type": "action"},
        ]
        self.ptree = ParameterTree()
        self.ptreedata = Parameter.create(name="Commands", type="group", children=self.params)
        self.ptree.setParameters(self.ptreedata)
        self.ptree.setMaximumWidth(300)
        self.ptree.setMinimumWidth(250)

    def command_dispatcher(self, param, changes):
        """
        Dispatcher for the commands from parametertree
        path[0] will be the command name
        path[1] will be the parameter (if there is one)
        path[2] will have the subcommand, if there is one
        data will be the field data (if there is any)
        """
        for param, change, data in changes:
            path = self.ptreedata.childPath(param)
            print("Path: ", path)
            if path[0] == "Quit":
                self.quit()
            elif path[0] == "Get Protocol":
                self.getProtocolDir()
                self.update_traces()
            elif path[0] == "Reload Last Protocol":
                self.getProtocolDir(reload_last=True)
                self.update_traces()
            elif path[0] == "Verbose":
                self.verbose = data
            elif path[0] == "Show Fitting Pars":
                print("Fitting Parameters: ")
                if self.MINC is not None:
                    self.MINC.show_fitting_pars()
                else:
                    print("Analysis not performed yet")
            elif path[0] == "Copy Fit to template":
                self.copy_fits()
            elif path[0] == "Write Dataset text":
                self.write_dataset()
            elif path[0] == "Reload":
                self.reload()
            elif path[0] == "Compare Events":
                self.compare_flag = data
                print("compare flg: ", self.compare_flag)
                self.compareEvents()
            elif path[0] == "PreProcessing":
                if path[1] == "Channel Name":
                    self.ampdataname = data
                elif path[1] == "Enable Filtering":
                    self.filters.enabled = data
                elif path[1] == "Detrend Method":
                    self.filters.Detrend_method = data
                elif path[1] == "LPF":
                    self.filters.LPF_frequency = data
                elif path[1] == "HPF":
                    self.filters.HPF_frequency = data
                elif path[1] == "Notch Frequency":
                    if isinstance(data, str):
                        if data == "60HzHarm+4K":
                            data = self.notch_60HzHarmonics_4K
                        elif data == "60HzHarm":
                            data = self.notch_60HzHarmonics
                        self.filters.Notch_frequencies = data
                elif path[1] == "Notch Q":
                    self.filters.Notch_Q = data
                elif path[1] == "Set Start (s)":
                    self.tstart = data
                elif path[1] == "Set End (s)":
                    if data > self.tstart:
                        self.tend = data
                    else:
                        pass
                # elif path[0] == "Apply Filters":
                #     self.update_traces(update_analysis=False)
                else:
                    print("argument: ", path[1], "is not handled in: ", path[0])
                    raise ValueError()

            elif path[0] == "Mini Analysis":
                if path[1] == "Rise Tau":
                    self.tau1 = data
                    print(self.tau1)
                elif path[1] == "Fall Tau":
                    self.tau2 = data
                    print(self.tau2)
                elif path[1] == "Order":
                    self.Order = data
                elif path[1] == "sign":
                    self.minis_sign = data
                    # self.update_traces(update_analysis=True)
                elif path[1] == "Threshold":
                    self.thresh_reSD = data
                    self.update_threshold()
                elif path[1] == "Method":
                    self.last_method = data
                elif path[1] == "Analyze Events":  # call the analysis function
                    self.update_analysis()

                else:
                    print("argument: ", path[1], "is not handled in: ", path[0])
                    raise ValueError()

            elif path[0] == "Reload":
                self.reload()
            else:
                print(f"**** Command {path[0]:s} was not parsed in command dispatcher")

    def reload(self):
        print("reloading...")
        importlib.invalidate_caches()
        for module in all_modules:
            print("reloading: ", module)
            module = reload(module, debug=False)
            # module = importlib.reload(module)

        self.MINC = minicalcs.MiniCalcs(parent=self)

    def set_window(self, parent=None):
        super(MiniViewer, self).__init__(parent=parent)
        self.win = pg.GraphicsLayoutWidget(title="MiniViewer")
        layout = pg.Qt.QtWidgets.QGridLayout()
        layout.setSpacing(8)
        self.win.setLayout(layout)
        self.win.resize(1280, 800)
        self.win.setWindowTitle("No File")
        self.buttons = pg.Qt.QtWidgets.QGridLayout()
        self.build_ptree()
        self.buttons.addWidget(self.ptree)
        self.ptreedata.sigTreeStateChanged.connect(self.command_dispatcher)

        self.w1 = Slider(0, 500, scalar=1.0, parent=parent)
        self.w1.setGeometry(0, 0, 500, 30)
        self.w1.slider.setSingleStep(1)
        self.w1.slider.setPageStep(1)
        self.w1.slider.valueChanged.connect(self.update_traces)

        # spacerItem = pg.QtGui.QSpacerItem(0, 10,
        # pg.QtGui.QSizePolicy.Expanding, pg.QtGui.QSizePolicy.Minimum)
        # self.buttons.addItem(spacerItem)

        self.dataplot = pg.PlotWidget()
        self.dataplot2 = pg.PlotWidget()
        self.dataplot2.setXLink(self.dataplot)
        self.threshold_line = pg.InfiniteLine(
            self.thresh_reSD,
            angle=0.0,
            pen="c",
            hoverPen="y",
            bounds=[0.0, 20.0],
            movable=True,
        )
        self.threshold_line_label = pg.InfLineLabel(
            self.threshold_line,
            text=f"Abs Thresh: {self.thresh_reSD:.3e}",
            movable=True,
            position=0.0,
        )
        self.dataplot2.addItem(self.threshold_line)
        self.threshold_line.sigDragged.connect(self.update_threshold)
        self.fitplot = pg.PlotWidget()
        self.histplot = pg.PlotWidget()
        self.xplot = pg.PlotWidget()
        # row, column, rowspan, colspan)
        layout.addLayout(self.buttons, 0, 0, 10, 1)
        self.dlayout = pg.QtWidgets.QGridLayout()
        self.dataplot.setMinimumHeight(500)
        self.dlayout.addWidget(self.dataplot, 0, 0, 3, 8)
        self.dlayout.addWidget(self.dataplot2, 3, 0, 1, 8)
        self.dlayout.addWidget(self.w1, 4, 0, 1, 8)
        self.dlayout.setColumnMinimumWidth(0, 650)
        layout.addLayout(self.dlayout, 0, 1, 1, 1)
        self.dsumlayout = pg.QtWidgets.QGridLayout()
        self.dsumlayout.addWidget(self.fitplot)  # , 0, 0)
        self.dsumlayout.addWidget(self.histplot)  # , 1, 0)
        self.dsumlayout.addWidget(self.xplot)  # , 2, 0)
        layout.addLayout(self.dsumlayout, 0, 9, 10, 1)
        # self.dsumlayout.setColumnMinimumWidth(0, 200)
        layout.setColumnStretch(0, 0)  # reduce width of LHS column of buttons
        layout.setColumnStretch(1, 20)  # and stretch out the data dispaly
        layout.setColumnStretch(2, 0)  # and stretch out the data dispaly

        self.keyPressed.connect(self.on_key)
        self.win.show()


class FloatSlider(pg.QtWidgets.QSlider):
    def __init__(self, parent, decimals=3, *args, **kargs):
        super(FloatSlider, self).__init__(parent, *args, **kargs)
        self._multi = 10**decimals
        self.setMinimum(self.minimum())
        self.setMaximum(self.maximum())

    def value(self):
        return float(super(FloatSlider, self).value()) / self._multi

    def setMinimum(self, value):
        self.min_val = value
        return super(FloatSlider, self).setMinimum(int(value * self._multi))

    def setMaximum(self, value):
        self.max_val = value
        return super(FloatSlider, self).setMaximum(int(value * self._multi))

    def setValue(self, value):
        super(FloatSlider, self).setValue(int((value - self.min_val) * self._multi))


class Slider(pg.QtWidgets.QWidget):
    def __init__(self, minimum, maximum, scalar=1.0, parent=None):
        super(Slider, self).__init__(parent=parent)
        self.verticalLayout = pg.Qt.QtWidgets.QVBoxLayout(self)
        self.label = pg.Qt.QtWidgets.QLabel(self)
        self.verticalLayout.addWidget(self.label, alignment=pg.QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.horizontalLayout = pg.Qt.QtWidgets.QHBoxLayout()
        # spacerItem = pg.QtGui.QSpacerItem(
        #     0, 20, pg.QtWidgets.QSizePolicy.PolicyFlag.ExpandFlag # , pg.QtWidgets.QSizePolicy.Minimum
        # )
        # self.horizontalLayout.addItem(spacerItem)
        self.slider = FloatSlider(self, decimals=0)
        self.slider.setOrientation(pg.QtCore.Qt.Orientation.Horizontal)
        self.horizontalLayout.addWidget(self.slider)
        # spacerItem1 = pg.QtGui.QSpacerItem(
        #     0, 20, pg.QtWidgets.QSizePolicy.PolicyFlag.ExpandFlag # , pg.QtWidgets.QSizePolicy.Minimum
        # )
        # self.horizontalLayout.addItem(spacerItem1)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.resize(self.sizeHint())

        self.minimum = minimum * scalar
        self.maximum = maximum * scalar
        self.scalar = scalar
        self.slider.setMinimum(self.minimum)
        self.slider.setMaximum(self.maximum - 1)
        # self.slider.setRange(self.minimum, self.maximum)
        self.slider.valueChanged.connect(self.setLabelValue)
        self.setLabelValue(self.slider.value())

    def setLabelValue(self, value):
        self.x = int(value)  # int((self.minimum + (float(value) / (self.slider.maximum()
        # - self.slider.minimum())) * (
        # self.maximum - self.minimum)) /self.scalar)
        # print(self.minimum, self.slider.minimum(),
        # self.maximum, self.slider.maximum(), self.scalar, value, self.x)
        self.label.setText(f"{self.x:4d}")

    def getPosValue(self, x):
        return int(
            (x - self.minimum)
            * (self.slider.maximum() - self.slider.minimum())
            / (self.maximum - self.minimum)
        )


def main():
    app = pg.QtWidgets.QApplication([])
    app.setStyle("Fusion")
    pg.setConfigOption("antialias", True)
    MV = MiniViewer(app)
    app.aboutToQuit.connect(
        MV.quit
    )  # prevent python exception when closing window with system control
    MV.set_window()

    if sys.flags.interactive != 1:
        pg.QtWidgets.QApplication.instance().exec()


if __name__ == "__main__":
    main()
