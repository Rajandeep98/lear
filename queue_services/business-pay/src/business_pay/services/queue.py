# Copyright © 2024 Province of British Columbia
#
# Licensed under the BSD 3 Clause License, (the "License");
# you may not use this file except in compliance with the License.
# The template for the license can be found here
#    https://opensource.org/license/bsd-3-clause/
#
# Redistribution and use in source and binary forms,
# with or without modification, are permitted provided that the
# following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS “AS IS”
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""This provides the service to publish to the queue."""
import asyncio
import json
import logging
import random
import string

import nest_asyncio  # noqa: I001
from flask import g
from flask import current_app
from nats.aio.client import (
    Client as NATS,
    DEFAULT_CONNECT_TIMEOUT,
)  # noqa N814; by convention the name is NATS
from stan.aio.client import Client as STAN  # noqa N814; by convention the name is STAN


class QueueService:
    """Provides services to use the Queue from Flask.

    For ease of use, this follows the style of a Flask Extension
    """

    def __init__(self, app=None, loop=None):
        """Initialize, supports setting the app context on instantiation."""
        # Default NATS Options
        self.name = "default_api_client"
        self.nats_options = {}
        self.stan_options = {}
        self.loop = loop
        self.nats_servers = None
        self.subject = None
        self._nats = None
        self._stan = None

        self.logger = logging.getLogger()

        if app is not None:
            self.init_app(app, self.loop)

    def init_app(self, app, loop=None, nats_options=None, stan_options=None):
        """Initialize the extension.

        :param app: Flask app
        :return: naked
        """
        nest_asyncio.apply()
        self.name = app.config.get("NATS_CLIENT_NAME")
        self.loop = loop or asyncio.get_event_loop()
        # self.nats_servers = app.config.get('NATS_SERVERS').split(',')
        self.nats_servers = app.config.get("NATS_SERVERS")
        self.subject = app.config.get("NATS_FILER_SUBJECT")

        default_nats_options = {
            "name": self.name,
            "io_loop": self.loop,
            "servers": self.nats_servers,
            "connect_timeout": app.config.get(
                "NATS_CONNECT_TIMEOUT", DEFAULT_CONNECT_TIMEOUT
            ),
            # NATS handlers
            "error_cb": self.on_error,
            "closed_cb": self.on_close,
            "reconnected_cb": self.on_reconnect,
            "disconnected_cb": self.on_disconnect,
        }
        if not nats_options:
            nats_options = {}

        self.nats_options = {**default_nats_options, **nats_options}

        default_stan_options = {
            "cluster_id": app.config.get("NATS_CLUSTER_ID"),
            "client_id": (self.name.lower().strip(string.whitespace)).translate(
                {ord(c): "_" for c in string.punctuation}
            )
            + "_"
            + str(random.SystemRandom().getrandbits(0x58)),
        }
        if not stan_options:
            stan_options = {}

        self.stan_options = {**default_stan_options, **stan_options}

        app.teardown_appcontext(self.teardown)

    def teardown(
        self, exception
    ):  # pylint: disable=unused-argument; flask method signature
        """Destroy all objects created by this extension."""
        try:
            this_loop = self.loop or asyncio.get_event_loop()
            this_loop.run_until_complete(self.close())
        except RuntimeError as e:
            self.logger.error(e)

    async def connect(self):
        """Connect to the queueing service."""
        if current_app:
            if not hasattr(g, "nats"):
                g.nats = self._nats = NATS()
                g.stan = self._stan = STAN()
        if not self.nats:
            self._nats = NATS()
            self._stan = STAN()

        if not self.nats.is_connected:
            self.stan_options = {**self.stan_options, **{"nats": self.nats}}
            await self._nats.connect(**self.nats_options)
            await self._stan.connect(**self.stan_options)

    async def close(self):
        """Close the connections to the queue."""
        if self.nats and self.nats.is_connected:
            await self.stan.close()
            await self.nats.close()

    def publish_json(self, payload=None, subject=None):
        """Publish the json payload to the Queue Service."""
        try:
            subject = subject or self.subject
            self.loop.run_until_complete(self.async_publish_json(payload, subject))
        except Exception as err:
            self.logger.error("Error: %s", err)
            raise err

    async def publish_json_to_subject(self, payload=None, subject=None):
        """Publish the json payload to the specified subject."""
        try:
            await self.async_publish_json(payload, subject)
        except Exception as err:
            self.logger.error("Error: %s", err)
            raise err

    async def async_publish_json(self, payload=None, subject=None):
        """Publish the json payload to the Queue Service."""
        if not self.is_connected:
            await self.connect()

        await self.stan.publish(
            subject=subject, payload=json.dumps(payload).encode("utf-8")
        )

    async def on_error(self, e):
        """Handle errors raised by the client library."""
        self.logger.warning("Error: %s", e)

    async def on_reconnect(self):
        """Invoke by the client library when attempting to reconnect to NATS."""
        self.logger.warning(
            "Reconnected to NATS at nats://%s",
            self.nats.connected_url.netloc if self.nats else "none",
        )

    async def on_disconnect(self):
        """Invoke by the client library when disconnected from NATS."""
        self.logger.warning("Disconnected from NATS")

    async def on_close(self):
        """Invoke by the client library when the NATS connection is closed."""
        self.logger.warning("Closed connection to NATS")

    @property
    def is_closed(self):
        """Return True if the connection toThe cluster is closed."""
        try:
            if self.nats:
                return self.nats.is_closed
            return True
        except RuntimeError as re:
            print(re)
            return True

    @property
    def is_connected(self):
        """Return True if connected to the NATS cluster."""
        if self.nats:
            return self.nats.is_connected
        return False

    @property
    def stan(self):
        """Return the STAN client for the Queue Service."""
        if self._stan:
            return self._stan
        if current_app:
            if not hasattr(g, "stan"):
                return None
            return g.stan
        return None

    @property
    def nats(self):
        """Return the NATS client for the Queue Service."""
        if self._nats:
            return self._nats
        if current_app:
            if not hasattr(g, "nats"):
                return None
            return g.nats
        return None
