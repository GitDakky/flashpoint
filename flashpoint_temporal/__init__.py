"""Flashpoint Temporal orchestration layer.

Durable, traceable agent waves on top of the stateless Flashpoint spawner.
Temporal is the brain (durability, retry, rate-limiting); the spawner is the
muscle (fast container ignition/teardown).
"""
