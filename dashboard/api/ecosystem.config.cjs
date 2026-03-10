const dotenv = require('dotenv');
const path = require('path');

const envPath = path.resolve(__dirname, '.env');
const parsed = dotenv.config({ path: envPath }).parsed || {};

module.exports = {
  apps: [{
    name: 'dashboard-api',
    script: 'server.js',
    cwd: __dirname,
    env: parsed
  }]
};
