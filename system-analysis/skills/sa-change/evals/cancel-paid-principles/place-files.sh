#!/usr/bin/env bash
# Кладёт входные файлы кейса (files/) в рабочую папку теста.
set -eu
cp -R "$(dirname "$0")/files/." .
