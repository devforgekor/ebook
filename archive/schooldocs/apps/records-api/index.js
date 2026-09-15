const express = require('express');
const app = express();
const PORT = process.env.PORT || 80;

app.use(express.json());

// 라우트 등록
app.use('/api', require('./src/routes/submit'));
app.use('/api', require('./src/routes/status'));
app.use('/api', require('./src/routes/view'));
app.use('/api/manage', require('./src/routes/approve'));
app.use('/api/manage', require('./src/routes/pending'));
app.use('/api/manage', require('./src/routes/cohorts'));
app.use('/api/manage', require('./src/routes/uploadMembers'));
app.use('/api/manage', require('./src/routes/closeCohort'));
app.use('/api/manage', require('./src/routes/manageAdmins'));

app.get('/health', (req, res) => {
  const now = new Date();
  const kstNow = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
  const day = kstNow.getDay();
  const hour = kstNow.getHours();
  const minute = kstNow.getMinutes();
  const timeValue = hour * 100 + minute;
  const isWeekday = day >= 1 && day <= 5;
  const isBusinessHour = isWeekday && (timeValue >= 830 && timeValue < 1730);
  res.json({
    status: 'ok',
    mode: isBusinessHour ? 'ACTIVE' : 'STANDBY',
    message: isBusinessHour ? '정상 운영 중입니다.' : '현재 업무 시간이 아닙니다. 서비스는 정상 동작하나, 응답이 느릴 수 있습니다.',
    timestamp: now.toISOString()
  });
});

app.get('/warmup', (req, res) => {
  // 컨테이너 깨우기만 담당 (아무 무거운 초기화 없음)
  res.set('Cache-Control', 'no-store');
  res.status(200).send('OK');
});

const server = app.listen(PORT, () => console.log(`Server running on port ${PORT}`));

process.on('SIGTERM', () => {
  console.log('SIGTERM received, closing server...');
  server.close(() => {
    console.log('Server closed, exiting.');
    process.exit(0);
  });
  setTimeout(() => {
    console.error('Forced shutdown after timeout');
    process.exit(1);
  }, 25000);
});
