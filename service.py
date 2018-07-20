# Copyright (c) 2016, Palo Alto Networks
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

# Author: Nathan Embery <nembery@paloaltonetworks.com>

"""
Palo Alto Networks dynamic content update downloader service

Provides a single REST API endpoint to download content updates

This software is provided without support, warranty, or guarantee.
Use at your own risk.

"""

import os

from flask import Flask
from flask import abort
from flask import render_template
from flask import request
from flask import send_file
from werkzeug.exceptions import BadRequest, HTTPException

from .content_downloader import ContentDownloader, LoginError, GetLinkError

# init flask context
app = Flask(__name__)

# declare our download cache base directory
download_dir = '/tmp/content_downloader/cache'


# default route -
# FIXME - provide simple swagger api docs
@app.route('/')
def index():
    """
    Default route, return simple HTML page
    :return:  index.htnl template
    """
    return render_template('index.html', title='PanOS Content Update Utility')


# download_content route
@app.route('/download_content', methods=['POST'])
def download_content():
    """
    Requires a JSON formatted payload with the following keys:
    username - paloaltonetworks support username / email
    password - paloaltonetworks support password
    package - appthreat, app, antivirus, wildfire, wildfire2, wf500, traps, clientless
    force_update - Defaults to True, setting this to false will return the first content update of the desired type
    found in the cache. Useful for repetitive calls

    :return: binary image containing content update
        HTTP-400 if required keys are missing
        HTTP-417 if support site format changes
        HTTP-401 if username / password auth fails
        HTTP-500 on application error
    """
    try:
        posted_json = request.get_json(force=True)

        username = posted_json['username']
        password = posted_json['password']
        package = posted_json['package']
        update = posted_json.get('force_update', "True")

    except BadRequest:
        return abort(500, 'Could not parse JSON payload')
    except HTTPException:
        return abort(500, 'Exception in request')
    except KeyError:
        return abort(400, 'not all keys present')

    package_dir = os.path.join(download_dir, package)
    print(package_dir)
    if not os.path.exists(package_dir):
        os.makedirs(package_dir)

    if str(update) == "False":
        # the user does not need the latest and greatest and just wants something relatively recent
        cached_files = os.listdir(package_dir)
        # do we have a previously downloaded file?
        if len(cached_files) > 0:
            # yep, just return here, if not, continue getting the latest update
            return send_file(os.path.join(package_dir, cached_files[0]))

    try:
        content_downloader = ContentDownloader(username=username, password=password, package=package,
                                           debug=True)
    except LoginError:
        return abort(401, 'Could not log in to support portal with supplied credentials')

    # Check latest version. Login if necessary.
    token, updates = content_downloader.check()

    filename, foldername, latestversion = content_downloader.find_latest_update(updates)

    # check out cache dir
    downloaded_versions = list()
    for f in os.listdir(download_dir):
        downloaded_versions.append(f)

    # Check if already downloaded latest and do nothing
    # FIXME - I'm sure this could use a bit more logic to grab the latest and greatest...
    if filename in downloaded_versions:
        return send_file(os.path.join(download_dir, filename))

    # Get download URL
    try:
        fileurl = content_downloader.get_download_link(token, filename, foldername)
    except GetLinkError:
        return abort(417, 'Could not find download link!')

    try:
        filename = content_downloader.download(download_dir, fileurl, filename)
    except HTTPException:
        # FIXME - what exceptions can happen here?
        return abort(500, 'Error downloading file')

    return send_file(os.path.join(download_dir, filename))


@app.before_first_request
def init_application():
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
