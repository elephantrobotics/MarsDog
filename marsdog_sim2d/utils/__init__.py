#!/usr/bin/env python
# -*- coding: UTF-8 -*-
from __future__ import annotations

import typing as T


def safe_float(value: T.Any, default: float | int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
