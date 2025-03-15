# Echo Downloader

[![PyPI](https://img.shields.io/pypi/v/echo-downloader)](https://pypi.org/project/echo-downloader/)
[![Python Versions](https://img.shields.io/pypi/pyversions/echo-downloader)](https://pypi.org/project/echo-downloader/)

Echo Downloader is an interactive command-line tool for downloading lectures from the `echo360.org.uk` website.
It supports downloading multiple lectures at once and provides an intuitive user-friendly interface.

## Features

- **Simple UI**: The downloader provides a simple UI for downloading lectures.
- **Multiple Downloads**: You can download multiple lectures simultaneously.
- **Download Progress**: The downloader shows the download progress for each lecture.
- **Path Completion**: The downloader provides path completion when selecting the download directory.
- **GUI For Path Selection**: The downloader provides a GUI for selecting the download directory.
- **Relative Path Support**: You can specify a relative path for the download directory.

## Requirements

- Python 3.10 or higher
- Python package installer (`pip`)
- [FFmpeg](https://www.ffmpeg.org/download.html) (must be added to the system PATH)

## Installation

### 1. Install from `PyPI` (Recommended)

```bash
pip install echo-downloader
```

### 2. Install from GitHub Releases

1. Go to the [Releases](https://github.com/anviks/echo-downloader/releases) page
2. Download the latest `.whl` file
3. Install the package using the following command:

```bash
pip install ./path/to/echo_downloader.whl
```

### Linux Users: wxPython Dependency

On Linux, `wxPython` may fail to build during installation. If you encounter issues, install it manually:

```bash
sudo apt install python3-wxgtk4.0
```

## Usage

Run the following command to start the downloader:

```bash
echo-downloader
```

## Demo

![Demo](./assets/demo.gif)

## Configuration

The downloader uses a configuration file to store preferences and settings. The configuration file is located at:

- **Windows**: `C:\Users\<username>\AppData\Roaming\EchoDownloader\config.yaml`
- **Linux**: `/home/<username>/.config/EchoDownloader/config.yaml`
- **macOS**: `/Users/<username>/Library/Application Support/EchoDownloader/config.yaml`

The default configuration file can be found [here](./echo_downloader/config.yaml).

## Logging

Echo Downloader logs events and errors to help with debugging. The log files are located at:

- **Windows**: `C:\Users\<username>\AppData\Local\EchoDownloader\Logs`
- **Linux**: `/home/<username>/.local/state/EchoDownloader/log`
- **macOS**: `/Users/<username>/Library/Logs/EchoDownloader`

If you encounter any issues, please open an issue and attach the log file of that execution.
