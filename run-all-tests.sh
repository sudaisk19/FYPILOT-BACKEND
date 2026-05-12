#!/bin/bash
set -e

echo "Cleaning old results..."
rm -rf allure-results allure-report
mkdir -p allure-results/playwright
mkdir -p allure-results/pytest

echo "Running pytest unit tests..."
pytest tests/unit/ -v

echo "Running Playwright API tests..."
cd playwright-api
npm run test:all
cp -r allure-results/. ../allure-results/playwright/
cd ..

echo "Generating combined Allure report..."
allure generate allure-results --clean -o allure-report

echo "Opening report..."
allure open allure-report
