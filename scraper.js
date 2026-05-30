import express from 'express';
import dotenv from 'dotenv';
import { chromium } from '@playwright/test';

dotenv.config();

const app = express();
const PORT = process.env.SCRAPER_PORT || 8080;

let healthy = true;

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function scrapeAPS() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
  });
  const page = await context.newPage();

  try {
    await page.goto(process.env.APS_LOGIN_URL, { waitUntil: 'domcontentloaded' });

    // Wait for the dashboard to actually render
    await page.waitForSelector('text=DASHBOARD', { timeout: 30000 });

    // First call: get summary (contains storageSign with the storageId)
    const summary = await page.evaluate(async () => {
      const res = await fetch('/ema/ajax/getDashboardApiAjax/getStorageSummaryProductionInfoAjax', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: 'isMultipleStorage=false',
      });
      return res.json();
    });

    // Extract storageId from storageSign (format: "0/B05000001612YYYYYYYY")
    const storageId = summary.storageSign?.split('/')[1]?.replace(/Y+$/, '') || null;

    // Second call: get current power time series
    const powerData = storageId ? await page.evaluate(async (sid) => {
      const res = await fetch('/ema/ajax/getDashboardApiAjax/getStoragePowerOnCurrentDayAjax', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: `date=${new Date().toISOString().slice(0,10).replace(/-/g,'')}&storageId=${sid}`,
      });
      return res.json();
    }, storageId) : null;

    const last = (arr) => arr ? parseInt(arr[arr.length - 1]) : null;

    await browser.close();
    healthy = true;

    return {
      soc_percent: parseInt(summary.SSOC),
      charged_kwh: parseFloat(summary.DE1),
      discharged_kwh: parseFloat(summary.DE0),
      charge_power_w: last(powerData?.chargePower),
      discharge_power_w: last(powerData?.dischargePower),
    };
  } catch (err) {
    await browser.close();
    throw err;
  }
}

app.get('/status', async (req, res) => {
  const maxAttempts = 3;
  let lastErr;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const result = await scrapeAPS();
      return res.json({ ...result, updated_at: new Date().toISOString() });
    } catch (err) {
      lastErr = err;
      console.error(`Scrape attempt ${attempt}/${maxAttempts} failed:`, err.message);
      if (attempt < maxAttempts) await sleep(attempt * 5000);
    }
  }

  healthy = false;
  res.status(500).json({ error: 'Scrape failed: ' + lastErr.message });
});

app.get('/health', (_req, res) => {
  if (healthy) return res.status(200).send('ok');
  res.status(503).send('unhealthy');
});

app.listen(PORT, () => {
  console.log(`APS scraper listening on port ${PORT}`);
});
