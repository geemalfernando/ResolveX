const { chromium } = require('playwright');
const fs = require('fs');
const paths = require('path');
const os = require('os');
(async () => {
 const path = paths.resolve(__dirname, '../data/processed/live_integration_verification.json');
 const screenshots = paths.join(os.tmpdir(), 'resolvex-browser');
 fs.mkdirSync(screenshots, {recursive:true});
 const report = JSON.parse(fs.readFileSync(path));
 const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const page = await browser.newPage({viewport:{width:1100,height:1000}});
 const errors=[];
 page.on('pageerror', e=>errors.push(e.message));
 for (const record of report.cases) {
  if (!record.response) {
   await page.goto(`http://127.0.0.1:5173/?case=${record.case_id}`);
   await page.getByText('This case has no saved verdict. Analysis persistence needs attention.', {exact:true}).waitFor();
   record.frontend_blocked = 'No persisted verdict: migration required';
   continue;
  }
  await page.goto(`http://127.0.0.1:5173/?case=${record.case_id}`);
  await page.getByText('AI Fault Assessment', {exact:true}).waitFor();
  const body=await page.locator('body').innerText();
  const verdict=record.response.verdict;
  const probabilities=Object.entries(verdict.class_probabilities);
  const checks={
   prediction: body.includes(`Prediction: ${verdict.fault_prediction}`),
   confidence: body.includes(`Model confidence: ${(verdict.confidence*100).toFixed(2)}%`),
   probabilities:probabilities.every(([party,p])=>body.includes(party)&&body.includes(`${(p*100).toFixed(2)}%`)),
   support_review: body.includes('Resolution: Human Support Review'),
   evidence:body.includes('Evidence')&&body.includes('Photo: Not required for lateness'),
   eta_separate:body.includes('ETA Prediction'),
   provenance:body.includes('not genuine historical fault determinations'),
  };
  record.frontend_checks=checks;
  await page.screenshot({path:paths.join(screenshots, `${record.expected.toLowerCase()}.png`),fullPage:true});
  console.log(record.expected,checks);
 }
 report.browser_errors=errors;
 fs.writeFileSync(path,JSON.stringify(report,null,2));
 await browser.close();
 if(errors.length||report.cases.some(r=>r.frontend_checks&&Object.values(r.frontend_checks).some(v=>!v))) process.exit(1);
})().catch(e=>{console.error(e);process.exit(1)});
