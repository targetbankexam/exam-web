/**
 * Target Bank Exam — PC Web Examination Portal
 * Complete Client-Side Engine Matching Guidely / TCS iON CBT Specifications
 */

// 1. Firebase Initialization
const firebaseConfig = {
  apiKey: "AIzaSyBCx_hL8NqhMxp3Zs_deRCUs7dY1IQJo8M",
  authDomain: "target-bank-exam-56101.firebaseapp.com",
  projectId: "target-bank-exam-56101",
  storageBucket: "target-bank-exam-56101.firebasestorage.app",
  messagingSenderId: "812514972398",
  appId: "1:812514972398:web:targetbankexamweb"
};

if (!firebase.apps.length) {
  firebase.initializeApp(firebaseConfig);
}

const auth = firebase.auth();
const db = firebase.firestore();

// App State
const state = {
  currentUser: null,
  activeSession: null,
  sessionCode: null,
  
  // Exam Questions & Section Routing
  allQuestions: [],
  sections: [], // [ { id: 'quant', name: 'Numerical Ability', questions: [...] }, ... ]
  currentSectionIdx: 0,
  currentQuestionIdx: 0, // index within current section
  
  selectedAnswers: {}, // { [questionId]: optionIndex }
  questionStatus: {},  // { [questionId]: 'not_visited' | 'not_answered' | 'answered' | 'marked' | 'marked_answered' }
  questionTimeSpent: {}, // { [questionId]: seconds }
  
  currentSectionTimerSeconds: 1200, // 20 minutes default per section
  sectionTimerInterval: null,
  isPaused: false,
  defaultLanguage: 'en',
  
  // Results
  examResult: null,
  
  // Solutions & Reattempt
  solCurrentQIdx: 0,
  isReattemptMode: false,
  reattemptSelections: {},
  reattemptChecked: {}
};

// DOM Elements
const authScreen = document.getElementById('authScreen');
const pairingScreen = document.getElementById('pairingScreen');
const instructionsScreen1 = document.getElementById('instructionsScreen1');
const instructionsScreen2 = document.getElementById('instructionsScreen2');
const cbtScreen = document.getElementById('cbtScreen');
const resultsScreen = document.getElementById('resultsScreen');
const solutionsScreen = document.getElementById('solutionsScreen');

const userBadge = document.getElementById('userBadge');
const userName = document.getElementById('userName');
const userAvatar = document.getElementById('userAvatar');
const signOutBtn = document.getElementById('signOutBtn');

// Instructions Elements
const instTitle1 = document.getElementById('instTitle1');
const instTitle2 = document.getElementById('instTitle2');
const instTotalDuration = document.getElementById('instTotalDuration');
const instTotalQuestions = document.getElementById('instTotalQuestions');
const instSectionsTableBody = document.getElementById('instSectionsTableBody');
const btnInstNext = document.getElementById('btnInstNext');
const btnInstPrev = document.getElementById('btnInstPrev');
const defaultLangSelect = document.getElementById('defaultLangSelect');
const declarationCheck = document.getElementById('declarationCheck');
const btnReadyToBegin = document.getElementById('btnReadyToBegin');

// CBT Elements
const cbtExamTitle = document.getElementById('cbtExamTitle');
const cbtTimerDisplay = document.getElementById('cbtTimerDisplay');
const cbtSidebarTimerDisplay = document.getElementById('cbtSidebarTimerDisplay');
const btnPauseExam = document.getElementById('btnPauseExam');
const btnFullscreenToggle = document.getElementById('btnFullscreenToggle');
const cbtSectionTabs = document.getElementById('cbtSectionTabs');
const cbtQnTimeDisplay = document.getElementById('cbtQnTimeDisplay');
const cbtQuestionNumberLabel = document.getElementById('cbtQuestionNumberLabel');
const cbtPassageCol = document.getElementById('cbtPassageCol');
const cbtPassageText = document.getElementById('cbtPassageText');
const cbtQuestionCol = document.getElementById('cbtQuestionCol');
const cbtQuestionText = document.getElementById('cbtQuestionText');
const cbtQuestionImages = document.getElementById('cbtQuestionImages');
const cbtOptionsGroup = document.getElementById('cbtOptionsGroup');
const cbtCandidateName = document.getElementById('cbtCandidateName');
const cbtCandidateAvatar = document.getElementById('cbtCandidateAvatar');
const paletteSectionTitle = document.getElementById('paletteSectionTitle');
const cbtPaletteGrid = document.getElementById('cbtPaletteGrid');

// CBT Legend Counters
const legCountAnswered = document.getElementById('legCountAnswered');
const legCountNotAnswered = document.getElementById('legCountNotAnswered');
const legCountNotVisited = document.getElementById('legCountNotVisited');
const legCountMarked = document.getElementById('legCountMarked');
const legCountMarkedAnswered = document.getElementById('legCountMarkedAnswered');

// CBT Nav Buttons
const btnMarkReviewNext = document.getElementById('btnMarkReviewNext');
const btnClearResponse = document.getElementById('btnClearResponse');
const btnSaveNext = document.getElementById('btnSaveNext');
const btnSubmitSection = document.getElementById('btnSubmitSection');

// Submit Modal
const submitModal = document.getElementById('submitModal');
const submitModalTitle = document.getElementById('submitModalTitle');
const submitModalPrompt = document.getElementById('submitModalPrompt');
const btnCancelSubmitModal = document.getElementById('btnCancelSubmitModal');
const btnConfirmSubmitModal = document.getElementById('btnConfirmSubmitModal');

// Result Screen Elements (Redesigned Scorecard)
const resExamTitleDisplay = document.getElementById('resExamTitleDisplay');
const resCandidateName = document.getElementById('resCandidateName');
const resTestDate = document.getElementById('resTestDate');
const resScoreText = document.getElementById('resScoreText');
const resTotalQText = document.getElementById('resTotalQText');
const resCardScore = document.getElementById('resCardScore');
const resCardAttempted = document.getElementById('resCardAttempted');
const resCardCorrect = document.getElementById('resCardCorrect');
const resCardIncorrect = document.getElementById('resCardIncorrect');
const resCardSkipped = document.getElementById('resCardSkipped');
const resCardUnseen = document.getElementById('resCardUnseen');
const resCardAccuracy = document.getElementById('resCardAccuracy');
const resCardTotalTime = document.getElementById('resCardTotalTime');
const resCardUtilizedTime = document.getElementById('resCardUtilizedTime');
const resCardWastedTime = document.getElementById('resCardWastedTime');
const btnResultBackToHome = document.getElementById('btnResultBackToHome');
const btnResultEnterNewCode = document.getElementById('btnResultEnterNewCode');
const btnGoToSolutions = document.getElementById('btnGoToSolutions');
const btnInstBackToOTP = document.getElementById('btnInstBackToOTP');
const solBtnBackToOTP = document.getElementById('solBtnBackToOTP');

// Solutions Screen Elements (Matching Photos 1, 2, 3, 4)
const solExamTitle = document.getElementById('solExamTitle');
const solBtnResults = document.getElementById('solBtnResults');
const solCandidateName = document.getElementById('solCandidateName');
const solSectionTabs = document.getElementById('solSectionTabs');
const solReattemptToggle = document.getElementById('solReattemptToggle');
const solTimeBadgeText = document.getElementById('solTimeBadgeText');
const solLangSelect = document.getElementById('solLangSelect');

const solQNumberGlobal = document.getElementById('solQNumberGlobal');
const solSectionBadge = document.getElementById('solSectionBadge');
const solBtnBookmark = document.getElementById('solBtnBookmark');
const solBtnReport = document.getElementById('solBtnReport');

const solBifurcatedView = document.getElementById('solBifurcatedView');
const solPassageHeader = document.getElementById('solPassageHeader');
const solPassageContent = document.getElementById('solPassageContent');
const solPassageImages = document.getElementById('solPassageImages');
const solBifurcatedSubQ = document.getElementById('solBifurcatedSubQ');
const solBifurcatedSubQImages = document.getElementById('solBifurcatedSubQImages');
const solBifurcatedOptions = document.getElementById('solBifurcatedOptions');
const solBifurcatedReattemptAction = document.getElementById('solBifurcatedReattemptAction');
const btnCheckBifurcatedReattempt = document.getElementById('btnCheckBifurcatedReattempt');
const solBifurcatedSolutionBlock = document.getElementById('solBifurcatedSolutionBlock');
const solBifurcatedSolutionText = document.getElementById('solBifurcatedSolutionText');

const solSingleView = document.getElementById('solSingleView');
const solSingleQText = document.getElementById('solSingleQText');
const solSingleQImages = document.getElementById('solSingleQImages');
const solSingleOptions = document.getElementById('solSingleOptions');
const solSingleReattemptAction = document.getElementById('solSingleReattemptAction');
const btnCheckSingleReattempt = document.getElementById('btnCheckSingleReattempt');
const solSingleSolutionBlock = document.getElementById('solSingleSolutionBlock');
const solSingleSolutionText = document.getElementById('solSingleSolutionText');

const solBtnPrev = document.getElementById('solBtnPrev');
const solBtnNext = document.getElementById('solBtnNext');

const solSidebarToggle = document.getElementById('solSidebarToggle');
const solSidebarToggleIcon = document.getElementById('solSidebarToggleIcon');
const solRightSidebar = document.getElementById('solRightSidebar');

const solSecMark = document.getElementById('solSecMark');
const solSecAttempted = document.getElementById('solSecAttempted');
const solSecCorrect = document.getElementById('solSecCorrect');
const solSecIncorrect = document.getElementById('solSecIncorrect');
const solSecTime = document.getElementById('solSecTime');
const solPaletteGrid = document.getElementById('solPaletteGrid');

const btnQuickDemoSolutions = document.getElementById('btnQuickDemoSolutions');
const btnQuickDemoCBT = document.getElementById('btnQuickDemoCBT');

// Pairing Inputs
const digitInputs = [
  document.getElementById('digit1'),
  document.getElementById('digit2'),
  document.getElementById('digit3'),
  document.getElementById('digit4'),
  document.getElementById('digit5'),
  document.getElementById('digit6')
];
const connectCodeBtn = document.getElementById('connectCodeBtn');
const pairingAlert = document.getElementById('pairingAlert');

// Lightbox
const lightboxModal = document.getElementById('lightboxModal');
const lightboxImg = document.getElementById('lightboxImg');

// ==========================================
// 2. Navigation & UI Helpers
// ==========================================
function showScreen(screen) {
  [authScreen, pairingScreen, instructionsScreen1, instructionsScreen2, cbtScreen, resultsScreen, solutionsScreen].forEach(s => {
    if (s) s.classList.remove('active');
  });
  if (screen) screen.classList.add('active');
  window.scrollTo(0, 0);

  // Header visibility (only on auth & pairing screens)
  const appHeader = document.getElementById('appHeader');
  if (appHeader) {
    appHeader.style.display = (screen === authScreen || screen === pairingScreen) ? 'flex' : 'none';
  }
}

function showAlert(element, message, type = 'error') {
  element.textContent = message;
  element.className = `status-alert ${type}`;
  element.style.display = 'block';
}

function hideAlert(element) {
  element.style.display = 'none';
}

function convertDriveLink(url) {
  if (!url || typeof url !== 'string') return null;
  const trimmed = url.trim();
  if (!trimmed) return null;
  const match = trimmed.match(/(?:\/file\/d\/|\/d\/|[?&]id=)([a-zA-Z0-9_-]+)/);
  if (match && match[1]) {
    return `https://lh3.googleusercontent.com/d/${match[1]}`;
  }
  return trimmed;
}

function renderMath(element) {
  if (!element || !window.renderMathInElement) return;
  try {
    window.renderMathInElement(element, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '$', right: '$', display: false },
        { left: '\\(', right: '\\)', display: false },
        { left: '\\[', right: '\\]', display: true }
      ],
      throwOnError: false
    });
  } catch (e) {
    console.warn('KaTeX notice:', e);
  }
}

function formatTextWithImages(text, images) {
  if (!text) return '';
  const validImages = (images || []).map(convertDriveLink).filter(Boolean);

  // 1. Normalize linebreaks
  let str = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  // 2. Replace embedded image tags [img1], [img2]
  str = str.replace(/\[img(\d+)\]/gi, (match, p1) => {
    const idx = parseInt(p1, 10) - 1;
    if (idx >= 0 && idx < validImages.length) {
      return `<div class="content-img-wrap"><img src="${validImages[idx]}" alt="Diagram" class="content-img" onclick="openLightbox('${validImages[idx]}')"></div>`;
    }
    return '';
  });

  // 3. Markdown Bold (**text** -> <strong>text</strong>)
  str = str.replace(/\*\*(.+?)\*\*/gs, '<strong>$1</strong>');

  // 4. Markdown Italic (*text* -> <em>$1</em>, avoiding math asterisks)
  str = str.replace(/(?<!\*)\*([^\*\n]+?)\*(?!\*)/g, '<em>$1</em>');

  // 5. Bullet items (* item or - item at start of lines)
  str = str.replace(/(?:^|\n)[*-]\s+(.+?)(?=\n|$)/g, '\n<div class="bullet-item"><span class="bullet-dot">•</span><span>$1</span></div>');

  // 6. Paragraph gaps (multiple consecutive newlines -> compact gap)
  str = str.replace(/\n{2,}/g, '<div class="para-gap"></div>');

  // 7. Single newlines -> <br>
  str = str.replace(/\n/g, '<br>');

  // 8. Trim redundant breaks around display math $$...$$ and \[...\]
  str = str.replace(/(?:<br>|\s)*\$\$((?:.|\n)*?)\$\$(?:<br>|\s)*/g, (match, formula) => {
    return `$$${formula.trim()}$$`;
  });
  str = str.replace(/(?:<br>|\s)*\\\[((?:.|\n)*?)\\\](?:<br>|\s)*/g, (match, formula) => {
    return `\\[${formula.trim()}\\]`;
  });

  // 9. Clean up redundant breaks adjacent to para-gap and bullet-item
  str = str.replace(/<div class="para-gap"><\/div><br>/g, '<div class="para-gap"></div>');
  str = str.replace(/<br><div class="para-gap"><\/div>/g, '<div class="para-gap"></div>');
  str = str.replace(/<br>(<div class="bullet-item">)/g, '$1');
  str = str.replace(/(<\/div>)<br>/g, '$1');

  return str;
}

function returnToPairingScreen() {
  if (state.sectionTimerInterval) {
    clearInterval(state.sectionTimerInterval);
    state.sectionTimerInterval = null;
  }
  state.activeSession = null;
  state.sessionCode = null;
  state.selectedAnswers = {};
  state.questionStatus = {};
  state.questionTimeSpent = {};
  state.examResult = null;
  state.isReattemptMode = false;
  state.reattemptSelections = {};
  state.reattemptChecked = {};

  // Clear 6-digit input boxes
  digitInputs.forEach(i => { if (i) i.value = ''; });
  if (connectCodeBtn) {
    connectCodeBtn.disabled = true;
    connectCodeBtn.textContent = 'Start on PC';
  }
  hideAlert(pairingAlert);

  showScreen(pairingScreen);
  if (digitInputs[0]) digitInputs[0].focus();
}

if (btnResultBackToHome) btnResultBackToHome.addEventListener('click', returnToPairingScreen);
if (btnResultEnterNewCode) btnResultEnterNewCode.addEventListener('click', returnToPairingScreen);
if (solBtnBackToOTP) solBtnBackToOTP.addEventListener('click', returnToPairingScreen);
if (btnInstBackToOTP) btnInstBackToOTP.addEventListener('click', returnToPairingScreen);

window.openLightbox = function(url) {
  lightboxImg.src = url;
  lightboxModal.classList.add('active');
};
lightboxModal.addEventListener('click', () => lightboxModal.classList.remove('active'));

// Fullscreen toggle
btnFullscreenToggle.addEventListener('click', () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
});

// ==========================================
// 3. Authentication Handling
// ==========================================
auth.onAuthStateChanged((user) => {
  state.currentUser = user;
  if (user) {
    const name = user.displayName || (user.email ? user.email.split('@')[0] : 'Candidate');
    if (userName) userName.textContent = name;
    if (user.photoURL && userAvatar) {
      userAvatar.src = user.photoURL;
      userAvatar.style.display = 'block';
    }
    if (userBadge) userBadge.style.display = 'flex';
  } else {
    if (userBadge) userBadge.style.display = 'none';
    // Ensure anonymous auth for Firestore permissions without showing any login UI
    firebase.auth().signInAnonymously().catch(() => {});
  }
  // The web exam portal is strictly OTP-based: always start on the pairing/PIN screen
  showScreen(pairingScreen);
  if (digitInputs[0]) digitInputs[0].focus();
});

const googleSignInBtn = document.getElementById('googleSignInBtn');
if (googleSignInBtn) {
  googleSignInBtn.addEventListener('click', async () => {
    try {
      const provider = new firebase.auth.GoogleAuthProvider();
      await auth.signInWithPopup(provider);
    } catch (err) {
      showAlert(document.getElementById('authAlert'), err.message || 'Google sign in failed');
    }
  });
}

if (signOutBtn) {
  signOutBtn.addEventListener('click', () => auth.signOut());
}

// ==========================================
// 4. 6-Digit Pairing Logic
// ==========================================
digitInputs.forEach((input, index) => {
  input.addEventListener('input', (e) => {
    const val = e.target.value.replace(/[^0-9]/g, '');
    e.target.value = val;
    if (val && index < digitInputs.length - 1) digitInputs[index + 1].focus();
    checkCodeComplete();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Backspace' && !input.value && index > 0) digitInputs[index - 1].focus();
  });
  input.addEventListener('paste', (e) => {
    e.preventDefault();
    const pasteData = (e.clipboardData || window.clipboardData).getData('text');
    const digits = pasteData.replace(/[^0-9]/g, '').slice(0, 6);
    if (digits.length) {
      digits.split('').forEach((d, i) => { if (digitInputs[i]) digitInputs[i].value = d; });
      digitInputs[Math.min(digits.length, 5)].focus();
      checkCodeComplete();
    }
  });
});

function checkCodeComplete() {
  const code = digitInputs.map(i => i.value).join('');
  connectCodeBtn.disabled = code.length !== 6;
}

connectCodeBtn.addEventListener('click', async () => {
  const code = digitInputs.map(i => i.value).join('');
  if (code.length !== 6) return;

  hideAlert(pairingAlert);
  connectCodeBtn.disabled = true;
  connectCodeBtn.textContent = 'Verifying Code...';

  try {
    const docSnap = await db.collection('pc_sessions').doc(code).get();
    if (!docSnap.exists) {
      showAlert(pairingAlert, 'Invalid code. Please check your mobile app.');
      connectCodeBtn.disabled = false;
      connectCodeBtn.textContent = 'Start on PC';
      return;
    }

    const sessionData = docSnap.data();
    if (sessionData.expiresAt && Date.now() > sessionData.expiresAt) {
      showAlert(pairingAlert, 'Code expired. Please generate a new code on your phone.');
      connectCodeBtn.disabled = false;
      connectCodeBtn.textContent = 'Start on PC';
      return;
    }

    state.activeSession = sessionData;
    state.sessionCode = code;

    await db.collection('pc_sessions').doc(code).update({
      status: 'connected',
      connectedAt: Date.now()
    });

    await loadExamDataAndShowInstructions(sessionData);

  } catch (err) {
    showAlert(pairingAlert, err.message || 'Error connecting to exam session');
    connectCodeBtn.disabled = false;
    connectCodeBtn.textContent = 'Start on PC';
  }
});

// ==========================================
// 5. Exam Loading & Section Organization
// ==========================================
async function loadExamDataAndShowInstructions(session) {
  const examId = session.examId || 'sbi_clerk';
  // Cache busting: prevent browsers or GitHub Pages from serving stale cached JSON files
  const response = await fetch(`data/${examId}.json?_v=${Date.now()}`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Could not load questions for ${examId}`);
  const examJson = await response.json();
  const allQ = examJson.questions || [];

  // 1. Robustly extract requested DPP Day (handles int, string, day/dppDay keys, or regex from title)
  let requestedDay = null;
  if (session.dppDay !== undefined && session.dppDay !== null && session.dppDay !== '') {
    requestedDay = parseInt(session.dppDay, 10);
  } else if (session.day !== undefined && session.day !== null && session.day !== '') {
    requestedDay = parseInt(session.day, 10);
  } else if (session.title) {
    const m = session.title.match(/day\s*(\d+)/i);
    if (m) requestedDay = parseInt(m[1], 10);
  }

  // Fallback to URL parameters if not specified in session
  if (!requestedDay || isNaN(requestedDay)) {
    const urlParams = new URLSearchParams(window.location.search);
    const dayParam = urlParams.get('day') || urlParams.get('dppDay') || urlParams.get('dpp');
    if (dayParam) requestedDay = parseInt(dayParam, 10);
  }

  // 2. Filter questions based on requestedDay or full test
  let questions = [];

  if (requestedDay !== null && !isNaN(requestedDay)) {
    // Primary filter: match number q.dppDay
    questions = allQ.filter(q => Number(q.dppDay) === requestedDay);
    // Secondary filter: match ID containing `_d${requestedDay}_`
    if (!questions.length) {
      questions = allQ.filter(q => q.id && q.id.toLowerCase().includes(`_d${requestedDay}_`));
    }
    // Record resolved dppDay on activeSession
    if (state.activeSession) {
      state.activeSession.dppDay = requestedDay;
    }
    session.dppDay = requestedDay;
  } else if (session.mode === 'dpp') {
    // If mode is 'dpp' but no specific day was requested, default to Day 1
    questions = allQ.filter(q => Number(q.dppDay) === 1 || (q.id && q.id.toLowerCase().includes('_d1_')));
    if (!questions.length) questions = allQ.slice(0, 35);
    session.dppDay = 1;
    if (state.activeSession) state.activeSession.dppDay = 1;
  } else {
    // Full mock test
    questions = allQ;
  }

  // If still empty for some reason, fallback safely to all questions
  if (!questions.length) {
    questions = allQ;
  }

  // If session specifies a particular sectionId (e.g. 'quant' or 'reasoning')
  if (session.sectionId) {
    const secTarget = session.sectionId.toLowerCase();
    const secFiltered = questions.filter(q => (q.sectionId || '').toLowerCase().includes(secTarget));
    if (secFiltered.length > 0) {
      questions = secFiltered;
    }
  }

  state.allQuestions = questions;

  // Organize questions in banking standard order:
  // 1. English Language (1-30), 2. Numerical Ability (31-65), 3. Reasoning Ability (66-100)
  const englishQuestions = questions.filter(q => (q.sectionId || '').toLowerCase().includes('eng'));
  const quantQuestions = questions.filter(q => {
    const s = (q.sectionId || '').toLowerCase();
    return s.includes('quant') || s.includes('num') || s.includes('math');
  });
  const reasoningQuestions = questions.filter(q => (q.sectionId || '').toLowerCase().includes('reason'));

  const sectionList = [];
  if (englishQuestions.length) sectionList.push({ id: 'english', name: 'English Language', questions: englishQuestions });
  if (quantQuestions.length) sectionList.push({ id: 'quant', name: 'Numerical Ability', questions: quantQuestions });
  if (reasoningQuestions.length) sectionList.push({ id: 'reasoning', name: 'Reasoning Ability', questions: reasoningQuestions });

  if (!sectionList.length) {
    sectionList.push({ id: 'general', name: 'Numerical Ability', questions: questions });
  }

  state.sections = sectionList;
  state.allQuestions = sectionList.flatMap(s => s.questions);
  state.currentSectionIdx = 0;
  state.currentQuestionIdx = 0;
  state.selectedAnswers = {};
  state.questionStatus = {};
  state.questionTimeSpent = {};

  state.allQuestions.forEach(q => {
    state.questionStatus[q.id] = 'not_visited';
    state.questionTimeSpent[q.id] = 0;
  });

  // Dynamic, clean title for the exam
  let cleanTitle = session.title;
  const currentDay = session.dppDay || requestedDay;
  if (!cleanTitle) {
    if (currentDay) {
      cleanTitle = `SBI Clerk Prelims DPP Day ${currentDay}`;
    } else {
      cleanTitle = `${examId.toUpperCase()} Prelims Daily Practice Paper`;
    }
  } else {
    cleanTitle = cleanTitle
      .replace(/^sbi_clerk/i, 'SBI Clerk')
      .replace(/^ibps_clerk/i, 'IBPS Clerk')
      .replace(/^ibps_po/i, 'IBPS PO')
      .replace(/^sbi_po/i, 'SBI PO')
      .replace(/^rrb_clerk/i, 'RRB Clerk')
      .replace(/^rrb_po/i, 'RRB PO')
      .replace(/mock test/gi, 'Daily Practice Paper')
      .replace(/test/gi, 'Examination');
  }

  if (state.activeSession) {
    state.activeSession.title = cleanTitle;
  }

  instTitle1.textContent = cleanTitle;
  instTitle2.textContent = cleanTitle;
  cbtExamTitle.textContent = cleanTitle;
  if (solExamTitle) solExamTitle.textContent = cleanTitle;
  if (resExamTitleDisplay) resExamTitleDisplay.textContent = cleanTitle;

  // Duration: 20 min if single section DPP, or session.timerMinutes
  const totalMinutes = session.timerMinutes || (state.sections.length === 1 ? 20 : 60);
  instTotalDuration.textContent = totalMinutes;
  instTotalQuestions.textContent = state.allQuestions.length;

  // Build Sections Table in Instructions Page 1
  instSectionsTableBody.innerHTML = '';
  state.sections.forEach((sec, idx) => {
    const tr = document.createElement('tr');
    const secDuration = Math.round(totalMinutes / state.sections.length);
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${sec.name}</td>
      <td>${sec.questions.length}</td>
      <td>${sec.questions.length}</td>
      <td>${secDuration}</td>
    `;
    instSectionsTableBody.appendChild(tr);
  });

  showScreen(instructionsScreen1);
}

// Instructions Flow
btnInstNext.addEventListener('click', () => showScreen(instructionsScreen2));
btnInstPrev.addEventListener('click', () => showScreen(instructionsScreen1));

btnReadyToBegin.addEventListener('click', () => {
  if (!declarationCheck.checked) {
    alert('Please check the declaration box before proceeding.');
    return;
  }

  state.defaultLanguage = defaultLangSelect.value || 'en';

  // Request fullscreen mode for authentic exam feel
  document.documentElement.requestFullscreen().catch(() => {});

  // Start Section 1 (Quant)
  launchSection(0);
});

// ==========================================
// 6. CBT Examination Engine (Photo 3 & 4)
// ==========================================
function launchSection(sectionIdx) {
  state.currentSectionIdx = sectionIdx;
  state.currentQuestionIdx = 0;

  const section = state.sections[sectionIdx];
  paletteSectionTitle.textContent = section.name;

  // 20 minutes per section
  const totalMin = state.activeSession ? (state.activeSession.timerMinutes || 60) : 60;
  const secMin = Math.round(totalMin / state.sections.length);
  state.currentSectionTimerSeconds = secMin * 60;

  // Candidate Profile
  const cName = (state.currentUser && (state.currentUser.displayName || state.currentUser.email.split('@')[0])) 
    || (state.activeSession ? state.activeSession.candidateName : 'Candidate');
  cbtCandidateName.textContent = cName;
  cbtCandidateAvatar.textContent = cName.charAt(0).toUpperCase();

  // First question marked not answered
  if (section.questions.length) {
    state.questionStatus[section.questions[0].id] = 'not_answered';
  }

  buildSectionTabs();
  buildPalette();
  renderQuestion();
  startSectionTimer();

  showScreen(cbtScreen);
}

function buildSectionTabs() {
  cbtSectionTabs.innerHTML = '';
  state.sections.forEach((sec, idx) => {
    const tab = document.createElement('div');
    const isCurrent = idx === state.currentSectionIdx;
    const isSubmitted = idx < state.currentSectionIdx;
    const isLocked = idx > state.currentSectionIdx;

    tab.className = `cbt-sec-tab ${isCurrent ? 'active' : ''} ${isLocked ? 'locked' : ''}`;
    tab.innerHTML = `
      <span>${sec.name}</span>
      <span style="font-size: 11px; opacity: 0.8;">${isLocked ? '🔒' : (isSubmitted ? '✓' : '(i)')}</span>
    `;

    // Only allow clicking already completed sections if you want, or strictly lock:
    // User requested: "only when one section is submitted then only the other section is opened"
    cbtSectionTabs.appendChild(tab);
  });
}

function buildPalette() {
  cbtPaletteGrid.innerHTML = '';
  const currentSection = state.sections[state.currentSectionIdx];

  currentSection.questions.forEach((q, idx) => {
    const globalIdx = state.allQuestions.indexOf(q);
    const globalNum = globalIdx >= 0 ? (globalIdx + 1) : (idx + 1);

    const item = document.createElement('div');
    item.className = 'palette-item';
    item.id = `pal_q_${idx}`;
    item.textContent = globalNum;
    item.onclick = () => jumpToQuestion(idx);
    cbtPaletteGrid.appendChild(item);
  });

  updatePaletteStatus();
}

function updatePaletteStatus() {
  const currentSection = state.sections[state.currentSectionIdx];
  let ans = 0, notAns = 0, notVis = 0, mrk = 0, mrkAns = 0;

  currentSection.questions.forEach((q, idx) => {
    const el = document.getElementById(`pal_q_${idx}`);
    if (!el) return;

    const status = state.questionStatus[q.id] || 'not_visited';
    el.className = `palette-item status-${status.replace('_', '-')}`;
    if (idx === state.currentQuestionIdx) {
      el.classList.add('active-q');
    }

    if (status === 'answered') ans++;
    else if (status === 'not_answered') notAns++;
    else if (status === 'not_visited') notVis++;
    else if (status === 'marked') mrk++;
    else if (status === 'marked_answered') mrkAns++;
  });

  legCountAnswered.textContent = ans;
  legCountNotAnswered.textContent = notAns;
  legCountNotVisited.textContent = notVis;
  legCountMarked.textContent = mrk;
  legCountMarkedAnswered.textContent = mrkAns;
}

function renderQuestion() {
  const currentSection = state.sections[state.currentSectionIdx];
  const q = currentSection.questions[state.currentQuestionIdx];
  if (!q) return;

  const globalIdx = state.allQuestions.indexOf(q);
  const globalNum = globalIdx >= 0 ? (globalIdx + 1) : (state.currentQuestionIdx + 1);
  cbtQuestionNumberLabel.textContent = `Q: ${globalNum} / ${state.allQuestions.length}`;

  const isHi = state.defaultLanguage === 'hi';
  const qImages = (isHi && q.questionImagesHi && q.questionImagesHi.length) 
    ? q.questionImagesHi 
    : (q.questionImages || (q.questionImageDriveLink ? [q.questionImageDriveLink] : []));

  // Smart bifurcation check for set-based questions (Puzzles, RC, Parajumble, DI)
  const splitInfo = splitQuestion(q, state.allQuestions, globalIdx);

  if (splitInfo.isSet) {
    cbtPassageCol.style.display = 'block';
    cbtPassageText.innerHTML = formatTextWithImages(splitInfo.passage, qImages);
    renderMath(cbtPassageText);

    cbtQuestionText.innerHTML = formatTextWithImages(splitInfo.subQuestion, []);
  } else {
    cbtPassageCol.style.display = 'none';
    const qText = (isHi && q.questionTextHi) ? q.questionTextHi : q.questionText;
    cbtQuestionText.innerHTML = formatTextWithImages(qText, qImages);
  }
  renderMath(cbtQuestionText);

  // Render Options
  const options = (isHi && q.optionsHi && q.optionsHi.length) ? q.optionsHi : q.options;
  const letters = ['A', 'B', 'C', 'D', 'E', 'F'];
  const chosenOpt = state.selectedAnswers[q.id];

  cbtOptionsGroup.innerHTML = '';
  options.forEach((optText, oIdx) => {
    const row = document.createElement('div');
    row.className = `cbt-opt-row ${chosenOpt === oIdx ? 'selected' : ''}`;
    row.onclick = () => selectOption(oIdx);

    row.innerHTML = `
      <div class="cbt-opt-radio">
        <div class="cbt-opt-radio-dot"></div>
      </div>
      <div class="cbt-opt-text"><strong>${letters[oIdx]})</strong> ${optText}</div>
    `;
    renderMath(row.querySelector('.cbt-opt-text'));
    cbtOptionsGroup.appendChild(row);
  });

  // Submit button text: on last section, says "Submit", otherwise "Submit section"
  const isLastSec = state.currentSectionIdx === state.sections.length - 1;
  btnSubmitSection.textContent = isLastSec ? 'Submit' : 'Submit section';

  updatePaletteStatus();
}

function selectOption(index) {
  const currentSection = state.sections[state.currentSectionIdx];
  const q = currentSection.questions[state.currentQuestionIdx];

  if (state.selectedAnswers[q.id] === index) {
    // Deselect if already selected
    delete state.selectedAnswers[q.id];
    state.questionStatus[q.id] = 'not_answered';
  } else {
    state.selectedAnswers[q.id] = index;
    const curStatus = state.questionStatus[q.id];
    state.questionStatus[q.id] = (curStatus === 'marked' || curStatus === 'marked_answered') ? 'marked_answered' : 'answered';
  }

  renderQuestion();
}

function jumpToQuestion(newIdx) {
  const currentSection = state.sections[state.currentSectionIdx];
  if (newIdx < 0 || newIdx >= currentSection.questions.length) return;

  const currentQ = currentSection.questions[state.currentQuestionIdx];
  if (state.questionStatus[currentQ.id] === 'not_visited') {
    state.questionStatus[currentQ.id] = 'not_answered';
  }

  state.currentQuestionIdx = newIdx;
  const targetQ = currentSection.questions[newIdx];
  if (state.questionStatus[targetQ.id] === 'not_visited') {
    state.questionStatus[targetQ.id] = 'not_answered';
  }

  renderQuestion();
}

// CBT Navigation Buttons
btnSaveNext.addEventListener('click', () => {
  const currentSection = state.sections[state.currentSectionIdx];
  const q = currentSection.questions[state.currentQuestionIdx];
  const hasAns = state.selectedAnswers[q.id] !== undefined;

  state.questionStatus[q.id] = hasAns ? 'answered' : 'not_answered';

  if (state.currentQuestionIdx < currentSection.questions.length - 1) {
    jumpToQuestion(state.currentQuestionIdx + 1);
  } else {
    updatePaletteStatus();
  }
});

btnMarkReviewNext.addEventListener('click', () => {
  const currentSection = state.sections[state.currentSectionIdx];
  const q = currentSection.questions[state.currentQuestionIdx];
  const hasAns = state.selectedAnswers[q.id] !== undefined;

  state.questionStatus[q.id] = hasAns ? 'marked_answered' : 'marked';

  if (state.currentQuestionIdx < currentSection.questions.length - 1) {
    jumpToQuestion(state.currentQuestionIdx + 1);
  } else {
    updatePaletteStatus();
  }
});

btnClearResponse.addEventListener('click', () => {
  const currentSection = state.sections[state.currentSectionIdx];
  const q = currentSection.questions[state.currentQuestionIdx];
  delete state.selectedAnswers[q.id];
  state.questionStatus[q.id] = 'not_answered';
  renderQuestion();
});

// Section Timer & Per-Question Timer
function startSectionTimer() {
  if (state.sectionTimerInterval) clearInterval(state.sectionTimerInterval);

  updateTimerDisplays();

  state.sectionTimerInterval = setInterval(() => {
    if (state.isPaused) return;

    state.currentSectionTimerSeconds--;
    
    // Increment active question time
    const currentSection = state.sections[state.currentSectionIdx];
    if (currentSection && currentSection.questions[state.currentQuestionIdx]) {
      const qId = currentSection.questions[state.currentQuestionIdx].id;
      state.questionTimeSpent[qId] = (state.questionTimeSpent[qId] || 0) + 1;
    }

    updateTimerDisplays();

    if (state.currentSectionTimerSeconds <= 0) {
      clearInterval(state.sectionTimerInterval);
      alert(`Time is up for ${currentSection.name}! Submitting section.`);
      advanceToNextSectionOrFinalize();
    }
  }, 1000);
}

function updateTimerDisplays() {
  const m = Math.floor(state.currentSectionTimerSeconds / 60);
  const s = state.currentSectionTimerSeconds % 60;
  const formatted = `00 : ${String(m).padStart(2, '0')} : ${String(s).padStart(2, '0')}`;
  cbtTimerDisplay.textContent = formatted;
  cbtSidebarTimerDisplay.textContent = formatted;

  // Active question timer
  const currentSection = state.sections[state.currentSectionIdx];
  if (currentSection && currentSection.questions[state.currentQuestionIdx]) {
    const qId = currentSection.questions[state.currentQuestionIdx].id;
    const qSeconds = state.questionTimeSpent[qId] || 0;
    const qm = Math.floor(qSeconds / 60);
    const qs = qSeconds % 60;
    cbtQnTimeDisplay.textContent = `${String(qm).padStart(2, '0')}:${String(qs).padStart(2, '0')}`;
  }
}

btnPauseExam.addEventListener('click', () => {
  state.isPaused = !state.isPaused;
  btnPauseExam.textContent = state.isPaused ? 'Resume' : 'Pause';
});

// Section Submission
btnSubmitSection.addEventListener('click', () => {
  const isLast = state.currentSectionIdx === state.sections.length - 1;
  const currentSec = state.sections[state.currentSectionIdx];

  if (!isLast) {
    const nextSec = state.sections[state.currentSectionIdx + 1];
    submitModalTitle.textContent = `Submit ${currentSec.name}`;
    submitModalPrompt.textContent = `Are you sure you want to submit the ${currentSec.name} section? Once submitted, you cannot revisit these questions and the next section (${nextSec.name}) will begin.`;
  } else {
    submitModalTitle.textContent = 'Submit Examination';
    submitModalPrompt.textContent = 'Are you sure you want to submit your complete examination? Your score and performance will be finalized and synced to your mobile app.';
  }

  submitModal.classList.add('active');
});

btnCancelSubmitModal.addEventListener('click', () => submitModal.classList.remove('active'));

btnConfirmSubmitModal.addEventListener('click', () => {
  submitModal.classList.remove('active');
  advanceToNextSectionOrFinalize();
});

function advanceToNextSectionOrFinalize() {
  if (state.sectionTimerInterval) clearInterval(state.sectionTimerInterval);

  if (state.currentSectionIdx < state.sections.length - 1) {
    // Launch next section (Quant -> Reasoning -> English)
    launchSection(state.currentSectionIdx + 1);
  } else {
    // Final Examination Submission!
    finalizeExamSubmission();
  }
}

// ==========================================
// 7. Final Exam Submission & Sync (Photo 5)
// ==========================================
async function finalizeExamSubmission() {
  if (state.sectionTimerInterval) clearInterval(state.sectionTimerInterval);

  let correctCount = 0;
  let incorrectCount = 0;
  let attemptedCount = 0;
  let unattemptedCount = 0;
  let utilizedTime = 0;
  let wastedTime = 0;

  state.allQuestions.forEach(q => {
    const chosen = state.selectedAnswers[q.id];
    const timeSpent = state.questionTimeSpent[q.id] || 0;

    if (chosen !== undefined) {
      attemptedCount++;
      if (chosen === q.correctIndex) {
        correctCount++;
        utilizedTime += timeSpent;
      } else {
        incorrectCount++;
        wastedTime += timeSpent;
      }
    } else {
      unattemptedCount++;
      wastedTime += timeSpent;
    }
  });

  const totalQuestions = state.allQuestions.length;
  const unseenCount = state.allQuestions.filter(q => (state.questionStatus[q.id] || 'not_visited') === 'not_visited').length;
  const skippedCount = totalQuestions - attemptedCount;

  // Banking standard scoring: +1.00 correct, -0.25 wrong
  const rawScore = (correctCount * 1.0) - (incorrectCount * 0.25);
  const finalScore = Math.max(0, Math.round(rawScore * 100) / 100);
  const accuracy = attemptedCount > 0 ? Math.round((correctCount / attemptedCount) * 100) : 0;
  const totalTimeSeconds = utilizedTime + wastedTime;

  const resultPayload = {
    score: finalScore,
    maxScore: totalQuestions * 1.0,
    totalQuestions,
    answeredCount: attemptedCount,
    notAnsweredCount: skippedCount,
    correctCount,
    incorrectCount,
    unattemptedCount: skippedCount,
    accuracy,
    timeTakenSeconds: totalTimeSeconds,
    completedAt: new Date().toISOString(),
    answers: state.selectedAnswers,
    questionTimeSpent: state.questionTimeSpent
  };

  state.examResult = resultPayload;

  // Sync to Firestore
  try {
    if (state.sessionCode) {
      await db.collection('pc_sessions').doc(state.sessionCode).update({
        status: 'completed',
        result: resultPayload,
        completedAt: Date.now()
      });
    }

    const userId = state.currentUser ? state.currentUser.uid : (state.activeSession ? state.activeSession.userId : 'guest');
    const cName = state.currentUser ? (state.currentUser.displayName || state.currentUser.email.split('@')[0]) : 'Candidate';
    const examId = state.activeSession ? state.activeSession.examId : 'sbi_clerk';
    const dppDay = state.activeSession ? state.activeSession.dppDay : null;

    if (dppDay !== null && dppDay !== undefined) {
      const subKey = `${userId}_${examId}_dpp_${dppDay}`;
      const now = new Date();
      const istDate = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;

      await db.collection('dpp_submissions').doc(subKey).set({
        userId,
        candidateName: cName,
        examId,
        dppDay,
        score: finalScore,
        totalQuestions,
        timeTakenSeconds: totalTimeSeconds,
        istDate,
        submittedAt: now.toISOString()
      }, { merge: true });

      // Update leaderboards
      await updateFirestoreLeaderboardDoc(`${examId}_${userId}`, userId, cName, examId, finalScore, totalTimeSeconds);
      await updateFirestoreLeaderboardDoc(`all_${userId}`, userId, cName, 'all', finalScore, totalTimeSeconds);
    }
  } catch (syncErr) {
    console.warn('Firestore sync notice:', syncErr);
  }

  // Render Result Screen (Photo 5)
  renderResultScreen(finalScore, totalQuestions, attemptedCount, correctCount, incorrectCount, skippedCount, unseenCount, accuracy, totalTimeSeconds, utilizedTime, wastedTime);
}

async function updateFirestoreLeaderboardDoc(docId, userId, candidateName, examId, score, timeSeconds) {
  const docRef = db.collection('dpp_leaderboards').doc(docId);
  try {
    const snap = await docRef.get();
    if (!snap.exists) {
      await docRef.set({
        userId, candidateName, examId,
        dppsAttempted: 1, totalScore: score, averageScore: score,
        totalTimeSeconds: timeSeconds, averageTimeSeconds: timeSeconds,
        lastSubmittedAt: new Date().toISOString()
      });
    } else {
      const d = snap.data();
      const newDpps = (d.dppsAttempted || 0) + 1;
      const newScore = (d.totalScore || 0) + score;
      const newTime = (d.totalTimeSeconds || 0) + timeSeconds;
      await docRef.update({
        candidateName,
        dppsAttempted: newDpps,
        totalScore: newScore,
        averageScore: newScore / newDpps,
        totalTimeSeconds: newTime,
        averageTimeSeconds: newTime / newDpps,
        lastSubmittedAt: new Date().toISOString()
      });
    }
  } catch (_) {}
}

function renderResultScreen(score, totalQ, attempted, correct, incorrect, skipped, unseen, accuracy, totalTime, utilizedTime, wastedTime) {
  showScreen(resultsScreen);

  // Exam Title & Student Name
  const cTitle = (state.activeSession && state.activeSession.title) || 'SBI Clerk 2026 Prelims Daily Practice Paper';
  const cName = (state.currentUser && (state.currentUser.displayName || state.currentUser.email.split('@')[0]))
    || (state.activeSession ? state.activeSession.candidateName : 'Candidate');

  if (resExamTitleDisplay) resExamTitleDisplay.textContent = cTitle;
  if (resCandidateName) resCandidateName.textContent = cName;
  if (resTestDate) {
    const today = new Date();
    resTestDate.textContent = today.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  // Score
  const scoreFormatted = Number.isInteger(score) ? score.toString() : score.toFixed(2).replace(/\.00$/, '');
  if (resScoreText) resScoreText.textContent = scoreFormatted;
  if (resTotalQText) resTotalQText.textContent = totalQ;

  // 10 Cards
  if (resCardScore) resCardScore.textContent = `${scoreFormatted}/${totalQ}`;
  if (resCardAttempted) resCardAttempted.textContent = `${attempted}/${totalQ}`;
  if (resCardCorrect) resCardCorrect.textContent = `${correct}/${totalQ}`;
  if (resCardIncorrect) resCardIncorrect.textContent = `${incorrect}/${totalQ}`;
  if (resCardSkipped) resCardSkipped.textContent = `${skipped}/${totalQ}`;
  if (resCardUnseen) resCardUnseen.textContent = `${unseen}/${totalQ}`;

  if (resCardAccuracy) resCardAccuracy.textContent = `${accuracy}%`;

  function fmt(secs) {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  if (resCardTotalTime) resCardTotalTime.textContent = fmt(totalTime);
  if (resCardUtilizedTime) resCardUtilizedTime.textContent = fmt(utilizedTime);
  if (resCardWastedTime) resCardWastedTime.textContent = fmt(wastedTime);
}

// ==========================================
// 8. Solutions & Splitting Helpers (Photos 1-4)
// ==========================================
function getCommonPrefix(s1, s2) {
  if (!s1 || !s2) return '';
  const minLen = Math.min(s1.length, s2.length);
  let i = 0;
  while (i < minLen && s1[i] === s2[i]) i++;
  let prefix = s1.substring(0, i);
  if (prefix.includes('\n\n')) {
    prefix = prefix.substring(0, prefix.lastIndexOf('\n\n'));
  } else if (prefix.includes('.')) {
    prefix = prefix.substring(0, prefix.lastIndexOf('.') + 1);
  }
  return prefix.trim();
}

function splitQuestion(q, allQuestions, idx) {
  if (!q) return { isSet: false, passage: '', subQuestion: '' };

  const qText = (q.questionText || '').trim();

  // 1. Explicit passage or isSetBased flag
  if (q.passage && q.passage.trim().length > 0) {
    const p = q.passage.trim();
    let sub = (q.subQuestion || '').trim();
    if (!sub) {
      if (qText.startsWith(p)) {
        sub = qText.substring(p.length).trim();
      } else {
        const blocks = qText.split('\n\n');
        sub = blocks.length > 1 ? blocks[blocks.length - 1].trim() : qText;
      }
    }
    return { isSet: true, passage: p, subQuestion: sub };
  }

  // If marked explicitly as single
  if (q.isSetBased === false) {
    return { isSet: false, passage: '', subQuestion: qText };
  }

  // 2. DI / chart set with [img1]
  if (qText.includes('[img1]')) {
    const parts = qText.split('[img1]');
    if (parts.length >= 2 && parts[1].trim().length > 10) {
      return {
        isSet: true,
        passage: parts[0].trim() + '\n\n[img1]',
        subQuestion: parts[1].trim()
      };
    }
  }

  // 3. Common prefix with adjacent questions in same section
  if (allQuestions && allQuestions.length) {
    let bestPrefix = '';
    const mySec = q.sectionId;
    if (idx > 0 && allQuestions[idx - 1] && allQuestions[idx - 1].sectionId === mySec) {
      const p = getCommonPrefix(qText, (allQuestions[idx - 1].questionText || '').trim());
      if (p.length >= 80) bestPrefix = p;
    }
    if (idx < allQuestions.length - 1 && allQuestions[idx + 1] && allQuestions[idx + 1].sectionId === mySec) {
      const p = getCommonPrefix(qText, (allQuestions[idx + 1].questionText || '').trim());
      if (p.length > bestPrefix.length && p.length >= 80) bestPrefix = p;
    }
    if (bestPrefix && bestPrefix.length >= 80) {
      const rem = qText.substring(bestPrefix.length).trim();
      if (rem) return { isSet: true, passage: bestPrefix, subQuestion: rem };
    }
  }

  // 4. Passage starter patterns with question sentence
  const passageStarters = [
    'given below is a set of',
    'study the following information',
    'read the following passage',
    'in a certain code language',
    'a certain number of persons',
    'ten persons are sitting',
    'eight persons viz',
    'seven persons live',
    'seven persons were born',
    'nine boxes are kept',
    'six persons are sitting'
  ];
  const lower = qText.toLowerCase();
  if (passageStarters.some(ps => lower.startsWith(ps)) && qText.length >= 180) {
    const lines = qText.split('\n\n').map(l => l.trim()).filter(Boolean);
    if (lines.length >= 2) {
      const lastLine = lines[lines.length - 1];
      if (/^(Which|Who|What|How|Find|If|Where|When|In which|Select)/i.test(lastLine) || lastLine.endsWith('?')) {
        return {
          isSet: true,
          passage: lines.slice(0, -1).join('\n\n').trim(),
          subQuestion: lastLine
        };
      }
    }
  }

  return { isSet: false, passage: '', subQuestion: qText };
}

// ==========================================
// 9. Solutions Portal Controller (Photos 1-4)
// ==========================================
let solActiveSectionIdx = 0;

function getSectionIndexForQuestionIndex(qIdx) {
  if (!state.sections || !state.sections.length) return 0;
  let count = 0;
  for (let s = 0; s < state.sections.length; s++) {
    count += state.sections[s].questions.length;
    if (qIdx < count) return s;
  }
  return 0;
}

function getSectionStats(secIdx) {
  const sec = state.sections[secIdx];
  if (!sec) return { mark: '0.00', attempted: 0, correct: 0, incorrect: 0, time: '20m', total: 30 };

  let attempted = 0;
  let correct = 0;
  let incorrect = 0;
  let timeSeconds = 0;

  sec.questions.forEach(q => {
    const chosen = state.selectedAnswers[q.id];
    const t = state.questionTimeSpent[q.id] || 0;
    timeSeconds += t;

    if (chosen !== undefined) {
      attempted++;
      if (chosen === q.correctIndex) {
        correct++;
      } else {
        incorrect++;
      }
    }
  });

  const rawScore = (correct * 1.0) - (incorrect * 0.25);
  const mark = Math.max(0, Math.round(rawScore * 100) / 100);
  const timeMin = Math.round(timeSeconds / 60);
  const timeLabel = timeMin > 0 ? `${timeMin}m` : (timeSeconds > 0 ? `${timeSeconds}s` : '20m');

  return {
    mark: mark.toFixed(2).replace(/\.00$/, ''),
    attempted,
    correct,
    incorrect,
    time: timeLabel,
    total: sec.questions.length
  };
}

function renderSolutionsScreen() {
  if (!state.allQuestions || state.allQuestions.length === 0) {
    console.warn('No questions loaded in state.allQuestions!');
    return;
  }

  showScreen(solutionsScreen);

  // Set candidate name & title
  if (solCandidateName) {
    const cName = state.currentUser 
      ? (state.currentUser.displayName || state.currentUser.email.split('@')[0]) 
      : ((state.activeSession && state.activeSession.candidateName) || 'Candidate');
    solCandidateName.textContent = cName;
  }
  if (solExamTitle) {
    const dDay = (state.activeSession && state.activeSession.dppDay) || 8;
    const fallbackTitle = `SBI Clerk Prelims DPP Day ${dDay}`;
    const titleClean = (state.activeSession && state.activeSession.title) 
      ? state.activeSession.title 
      : fallbackTitle;
    solExamTitle.textContent = titleClean;
  }

  // Default to question index 0 if undefined
  if (state.solCurrentQIdx === undefined || state.solCurrentQIdx === null || state.solCurrentQIdx < 0) {
    state.solCurrentQIdx = 0;
  }

  solActiveSectionIdx = getSectionIndexForQuestionIndex(state.solCurrentQIdx);
  updateSolutionsSectionTabs();
  updateSolutionsSectionSummary(solActiveSectionIdx);
  buildSolutionsPalette();
  renderSolutionQuestion();
}

function updateSolutionsSectionTabs() {
  if (!solSectionTabs) return;
  solSectionTabs.innerHTML = '';

  state.sections.forEach((sec, idx) => {
    const btn = document.createElement('button');
    btn.className = `sol-sec-tab ${idx === solActiveSectionIdx ? 'active' : ''}`;
    btn.textContent = sec.name;
    btn.onclick = () => {
      solActiveSectionIdx = idx;
      // Jump to first question of this section
      let firstQIdx = 0;
      for (let s = 0; s < idx; s++) {
        firstQIdx += state.sections[s].questions.length;
      }
      state.solCurrentQIdx = firstQIdx;
      updateSolutionsSectionTabs();
      updateSolutionsSectionSummary(solActiveSectionIdx);
      buildSolutionsPalette();
      renderSolutionQuestion();
    };
    solSectionTabs.appendChild(btn);
  });
}

function updateSolutionsSectionSummary(secIdx) {
  const stats = getSectionStats(secIdx);
  if (solSecMark) solSecMark.textContent = `${stats.mark}/${stats.total}`;
  if (solSecAttempted) solSecAttempted.textContent = stats.attempted;
  if (solSecCorrect) solSecCorrect.textContent = stats.correct;
  if (solSecIncorrect) solSecIncorrect.textContent = stats.incorrect;
  if (solSecTime) solSecTime.textContent = stats.time;
  if (solTimeBadgeText) solTimeBadgeText.textContent = stats.time;
}

function buildSolutionsPalette() {
  if (!solPaletteGrid) return;
  solPaletteGrid.innerHTML = '';

  const activeSec = state.sections[solActiveSectionIdx];
  if (!activeSec) return;

  // Calculate start index in state.allQuestions
  let startIdx = 0;
  for (let s = 0; s < solActiveSectionIdx; s++) {
    startIdx += state.sections[s].questions.length;
  }

  activeSec.questions.forEach((q, secQIdx) => {
    const globalIdx = startIdx + secQIdx;
    const globalNum = globalIdx + 1;

    const item = document.createElement('div');
    item.className = `sol-palette-item ${globalIdx === state.solCurrentQIdx ? 'active' : ''}`;
    item.onclick = () => {
      state.solCurrentQIdx = globalIdx;
      buildSolutionsPalette();
      renderSolutionQuestion();
    };

    const chosen = state.selectedAnswers[q.id];
    let badgeClass = 'badge-skipped';

    if (chosen !== undefined) {
      if (chosen === q.correctIndex) {
        badgeClass = 'badge-correct';
      } else {
        badgeClass = 'badge-incorrect';
      }
    } else if (state.questionStatus[q.id] === 'not_visited') {
      badgeClass = 'badge-unseen';
    }

    const timeSpent = state.questionTimeSpent[q.id] || 0;
    let timeLabel = '-';
    if (chosen !== undefined && timeSpent > 0) {
      const m = Math.floor(timeSpent / 60);
      const s = timeSpent % 60;
      timeLabel = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }

    item.innerHTML = `
      <div class="sol-pentagon-badge ${badgeClass}">${globalNum}</div>
      <div class="sol-badge-time">${timeLabel}</div>
    `;

    solPaletteGrid.appendChild(item);
  });
}

function renderSolutionQuestion() {
  const q = state.allQuestions[state.solCurrentQIdx];
  if (!q) return;

  const globalIdx = state.solCurrentQIdx;
  const globalNum = globalIdx + 1;

  // Check if current question's section matches solActiveSectionIdx
  const expectedSecIdx = getSectionIndexForQuestionIndex(globalIdx);
  if (expectedSecIdx !== solActiveSectionIdx) {
    solActiveSectionIdx = expectedSecIdx;
    updateSolutionsSectionTabs();
    updateSolutionsSectionSummary(solActiveSectionIdx);
    buildSolutionsPalette();
  }

  // Update Question Info Bar (Question N of Total, Section Badge)
  if (solQNumberGlobal) {
    solQNumberGlobal.textContent = `Question ${globalNum} of ${state.allQuestions.length}`;
  }
  if (solSectionBadge) {
    const curSec = state.sections[solActiveSectionIdx];
    solSectionBadge.textContent = curSec ? curSec.name : (q.sectionId || 'General');
  }

  const isHi = (solLangSelect && solLangSelect.value === 'hi') || state.defaultLanguage === 'hi';
  const qText = (isHi && q.questionTextHi) ? q.questionTextHi : q.questionText;
  const qImages = (isHi && q.questionImagesHi && q.questionImagesHi.length) 
    ? q.questionImagesHi 
    : (q.questionImages || (q.questionImageDriveLink ? [q.questionImageDriveLink] : []));
  const options = (isHi && q.optionsHi && q.optionsHi.length) ? q.optionsHi : q.options;
  const letters = ['A', 'B', 'C', 'D', 'E', 'F'];
  const userChoice = state.selectedAnswers[q.id];
  const reChoice = state.reattemptSelections[q.id];
  const isReattemptChecked = state.reattemptChecked[q.id];

  // Smart bifurcation check
  const splitInfo = splitQuestion(q, state.allQuestions, globalIdx);

  // Clean solution text & images
  const explImages = (isHi && q.explanationImagesHi && q.explanationImagesHi.length) 
    ? q.explanationImagesHi 
    : (q.explanationImages || (q.explanationImageDriveLink ? [q.explanationImageDriveLink] : []));
  const validExplImages = (explImages || []).map(convertDriveLink).filter(Boolean);

  const explText = (isHi && q.explanationHi) ? q.explanationHi : (q.explanation || `Answer: ${letters[q.correctIndex]}`);
  const cleanExplText = explText.replace(/\*\*Answer:\s*[A-F]\*\*/i, '').trim();
  const explFormatted = `<strong>Answer: ${letters[q.correctIndex]}</strong>\n\n${cleanExplText}`;

  if (splitInfo.isSet) {
    // A. BIFURCATED VIEW (Photos 1, 2, 3)
    solBifurcatedView.style.display = 'flex';
    solSingleView.style.display = 'none';

    // Left constant passage pane
    if (solPassageHeader) {
      solPassageHeader.textContent = `Directions: Read the following information carefully and answer the questions that follow:`;
    }
    solPassageContent.innerHTML = formatTextWithImages(splitInfo.passage, qImages);
    renderMath(solPassageContent);

    if (solPassageImages) {
      if (!splitInfo.passage.includes('[img') && qImages.length > 0) {
        solPassageImages.innerHTML = qImages.map(convertDriveLink).filter(Boolean).map(imgUrl => 
          `<div class="content-img-wrap"><img src="${imgUrl}" alt="Passage Diagram" class="content-img" onclick="openLightbox('${imgUrl}')"></div>`
        ).join('');
      } else {
        solPassageImages.innerHTML = '';
      }
    }

    // Right variable question pane
    solBifurcatedSubQ.innerHTML = formatTextWithImages(splitInfo.subQuestion, []);
    renderMath(solBifurcatedSubQ);
    if (solBifurcatedSubQImages) solBifurcatedSubQImages.innerHTML = '';

    // Options
    solBifurcatedOptions.innerHTML = '';
    solBifurcatedOptions.className = `sol-options-group ${state.isReattemptMode ? 'reattempt-interactive' : ''}`;

    options.forEach((optText, oIdx) => {
      const row = document.createElement('div');
      row.className = 'sol-opt-row';

      if (state.isReattemptMode) {
        if (reChoice === oIdx) row.classList.add('selected');
        row.onclick = () => {
          if (!isReattemptChecked) {
            state.reattemptSelections[q.id] = oIdx;
            renderSolutionQuestion();
          }
        };
        if (isReattemptChecked) {
          if (oIdx === q.correctIndex) row.classList.add('opt-correct');
          else if (oIdx === reChoice) row.classList.add('opt-wrong');
        }
      } else {
        // Normal Solutions Mode: Green radio for correct, Red radio for user wrong
        if (oIdx === q.correctIndex) {
          row.classList.add('opt-correct');
        } else if (userChoice !== undefined && oIdx === userChoice) {
          row.classList.add('opt-wrong');
        }
      }

      row.innerHTML = `
        <div class="sol-opt-radio ${(!state.isReattemptMode || isReattemptChecked) ? (oIdx === q.correctIndex ? 'radio-correct' : (userChoice === oIdx || reChoice === oIdx ? 'radio-wrong' : '')) : ''}"></div>
        <div class="sol-opt-text"><strong>(${letters[oIdx]})</strong> ${optText}</div>
      `;
      renderMath(row.querySelector('.sol-opt-text'));
      solBifurcatedOptions.appendChild(row);
    });

    // Reattempt action & Solution block visibility
    if (state.isReattemptMode) {
      solBifurcatedReattemptAction.style.display = isReattemptChecked ? 'none' : 'block';
      solBifurcatedSolutionBlock.style.display = isReattemptChecked ? 'block' : 'none';
    } else {
      solBifurcatedReattemptAction.style.display = 'none';
      solBifurcatedSolutionBlock.style.display = 'block';
    }

    solBifurcatedSolutionText.innerHTML = formatTextWithImages(explFormatted, validExplImages);
    renderMath(solBifurcatedSolutionText);

    if (solBifurcatedSolutionImages) {
      if (!explFormatted.includes('[img') && validExplImages.length > 0) {
        solBifurcatedSolutionImages.innerHTML = validExplImages.map(imgUrl => 
          `<div class="content-img-wrap"><img src="${imgUrl}" alt="Solution Diagram" class="content-img" onclick="openLightbox('${imgUrl}')"></div>`
        ).join('');
      } else {
        solBifurcatedSolutionImages.innerHTML = '';
      }
    }

  } else {
    // B. SINGLE VIEW (Photo 4)
    solBifurcatedView.style.display = 'none';
    solSingleView.style.display = 'block';

    solSingleQText.innerHTML = formatTextWithImages(qText, qImages);
    renderMath(solSingleQText);

    if (solSingleQImages) {
      if (!qText.includes('[img') && qImages.length > 0) {
        solSingleQImages.innerHTML = qImages.map(convertDriveLink).filter(Boolean).map(imgUrl => 
          `<div class="content-img-wrap"><img src="${imgUrl}" alt="Question Diagram" class="content-img" onclick="openLightbox('${imgUrl}')"></div>`
        ).join('');
      } else {
        solSingleQImages.innerHTML = '';
      }
    }

    // Options
    solSingleOptions.innerHTML = '';
    solSingleOptions.className = `sol-options-group ${state.isReattemptMode ? 'reattempt-interactive' : ''}`;

    options.forEach((optText, oIdx) => {
      const row = document.createElement('div');
      row.className = 'sol-opt-row';

      if (state.isReattemptMode) {
        if (reChoice === oIdx) row.classList.add('selected');
        row.onclick = () => {
          if (!isReattemptChecked) {
            state.reattemptSelections[q.id] = oIdx;
            renderSolutionQuestion();
          }
        };
        if (isReattemptChecked) {
          if (oIdx === q.correctIndex) row.classList.add('opt-correct');
          else if (oIdx === reChoice) row.classList.add('opt-wrong');
        }
      } else {
        // Normal Solutions Mode
        if (oIdx === q.correctIndex) {
          row.classList.add('opt-correct');
        } else if (userChoice !== undefined && oIdx === userChoice) {
          row.classList.add('opt-wrong');
        }
      }

      row.innerHTML = `
        <div class="sol-opt-radio ${(!state.isReattemptMode || isReattemptChecked) ? (oIdx === q.correctIndex ? 'radio-correct' : (userChoice === oIdx || reChoice === oIdx ? 'radio-wrong' : '')) : ''}"></div>
        <div class="sol-opt-text"><strong>(${letters[oIdx]})</strong> ${optText}</div>
      `;
      renderMath(row.querySelector('.sol-opt-text'));
      solSingleOptions.appendChild(row);
    });

    // Reattempt action & Solution block visibility
    if (state.isReattemptMode) {
      solSingleReattemptAction.style.display = isReattemptChecked ? 'none' : 'block';
      solSingleSolutionBlock.style.display = isReattemptChecked ? 'block' : 'none';
    } else {
      solSingleReattemptAction.style.display = 'none';
      solSingleSolutionBlock.style.display = 'block';
    }

    solSingleSolutionText.innerHTML = formatTextWithImages(explFormatted, validExplImages);
    renderMath(solSingleSolutionText);

    if (solSingleSolutionImages) {
      if (!explFormatted.includes('[img') && validExplImages.length > 0) {
        solSingleSolutionImages.innerHTML = validExplImages.map(imgUrl => 
          `<div class="content-img-wrap"><img src="${imgUrl}" alt="Solution Diagram" class="content-img" onclick="openLightbox('${imgUrl}')"></div>`
        ).join('');
      } else {
        solSingleSolutionImages.innerHTML = '';
      }
    }
  }

  // Update Previous / Next Buttons
  if (solBtnPrev) solBtnPrev.disabled = globalIdx <= 0;
  if (solBtnNext) solBtnNext.disabled = globalIdx >= state.allQuestions.length - 1;

  // Highlight active badge in palette
  const allItems = solPaletteGrid.querySelectorAll('.sol-palette-item');
  const activeSec = state.sections[solActiveSectionIdx];
  let startIdx = 0;
  for (let s = 0; s < solActiveSectionIdx; s++) {
    startIdx += state.sections[s].questions.length;
  }
  const relativeIdx = globalIdx - startIdx;
  allItems.forEach((it, idx) => {
    it.classList.toggle('active', idx === relativeIdx);
  });
}

// Previous & Next Button Handlers
if (solBtnPrev) {
  solBtnPrev.addEventListener('click', () => {
    if (state.solCurrentQIdx > 0) {
      state.solCurrentQIdx--;
      renderSolutionQuestion();
    }
  });
}

if (solBtnNext) {
  solBtnNext.addEventListener('click', () => {
    if (state.solCurrentQIdx < state.allQuestions.length - 1) {
      state.solCurrentQIdx++;
      renderSolutionQuestion();
    }
  });
}

// Sidebar Collapse / Expand Toggle
if (solSidebarToggle) {
  solSidebarToggle.addEventListener('click', () => {
    const isCollapsed = solRightSidebar.classList.toggle('collapsed');
    if (solSidebarToggleIcon) {
      solSidebarToggleIcon.className = isCollapsed ? 'fa-solid fa-chevron-left' : 'fa-solid fa-chevron-right';
    }
  });
}

// Reattempt Mode Toggle Switch
if (solReattemptToggle) {
  solReattemptToggle.addEventListener('change', (e) => {
    state.isReattemptMode = e.target.checked;
    renderSolutionQuestion();
  });
}

// Check Answer in Reattempt Mode
if (btnCheckBifurcatedReattempt) {
  btnCheckBifurcatedReattempt.addEventListener('click', () => {
    const q = state.allQuestions[state.solCurrentQIdx];
    if (state.reattemptSelections[q.id] === undefined) {
      alert('Please select an option first!');
      return;
    }
    state.reattemptChecked[q.id] = true;
    renderSolutionQuestion();
  });
}

if (btnCheckSingleReattempt) {
  btnCheckSingleReattempt.addEventListener('click', () => {
    const q = state.allQuestions[state.solCurrentQIdx];
    if (state.reattemptSelections[q.id] === undefined) {
      alert('Please select an option first!');
      return;
    }
    state.reattemptChecked[q.id] = true;
    renderSolutionQuestion();
  });
}

// Top Bar Action Buttons
if (btnGoToSolutions) {
  btnGoToSolutions.addEventListener('click', () => {
    state.solCurrentQIdx = 0;
    state.isReattemptMode = false;
    state.reattemptSelections = {};
    state.reattemptChecked = {};
    if (solReattemptToggle) solReattemptToggle.checked = false;
    renderSolutionsScreen();
  });
}

if (solBtnResults) {
  solBtnResults.addEventListener('click', () => {
    if (state.examResult) {
      showScreen(resultsScreen);
    } else {
      calculateResults();
    }
  });
}

// Helpers for Direct / Query Param Testing (e.g. ?day=8&solutions=1 or ?code=123456)
function startExamWithData(sessionMeta = {}, examId = 'sbi_clerk') {
  const dDay = sessionMeta.dppDay || (state.activeSession ? state.activeSession.dppDay : 8);
  const autoTitle = (dDay && dDay > 1) 
    ? `SBI Clerk Prelims DPP Day ${dDay}` 
    : (dDay === 1 ? 'SBI Clerk Prelims DPP Day 1' : 'SBI Clerk 2026 Prelims Daily Practice Paper');

  state.activeSession = {
    examId: examId,
    mode: 'dpp',
    dppDay: dDay,
    title: sessionMeta.title || autoTitle,
    timerMinutes: sessionMeta.timerMinutes || (state.sections.length === 1 ? 20 : 40),
    candidateName: (state.currentUser && (state.currentUser.displayName || state.currentUser.email.split('@')[0])) || 'Candidate'
  };

  const titleClean = state.activeSession.title;
  instTitle1.textContent = titleClean;
  instTitle2.textContent = titleClean;
  cbtExamTitle.textContent = titleClean;
  if (solExamTitle) solExamTitle.textContent = titleClean;
  if (resExamTitleDisplay) resExamTitleDisplay.textContent = titleClean;

  const totalMinutes = state.activeSession.timerMinutes;
  instTotalDuration.textContent = totalMinutes;
  instTotalQuestions.textContent = state.allQuestions.length;

  instSectionsTableBody.innerHTML = '';
  state.sections.forEach((sec, idx) => {
    const tr = document.createElement('tr');
    const secDuration = Math.round(totalMinutes / state.sections.length);
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${sec.name}</td>
      <td>${sec.questions.length}</td>
      <td>${sec.questions.length}</td>
      <td>${secDuration}</td>
    `;
    instSectionsTableBody.appendChild(tr);
  });

  showScreen(instructionsScreen1);
}

async function loadDemoExamData(targetDay = 8) {
  try {
    const res = await fetch(`data/sbi_clerk.json?_v=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to load sbi_clerk.json');
    const examData = await res.json();
    const allQ = examData.questions || [];

    let chosenDay = targetDay;
    if (isNaN(chosenDay) || chosenDay < 1) chosenDay = 8;

    // Filter questions for chosen DPP Day
    let questions = allQ.filter(q => Number(q.dppDay) === chosenDay || (q.id && q.id.toLowerCase().includes(`_d${chosenDay}_`)));
    if (!questions.length) {
      console.warn(`No questions found for DPP Day ${chosenDay}, fallback to Day 1`);
      chosenDay = 1;
      questions = allQ.filter(q => Number(q.dppDay) === 1 || (q.id && q.id.toLowerCase().includes('_d1_')));
      if (!questions.length) questions = allQ.slice(0, 35);
    }

    state.activeSession = {
      examId: 'sbi_clerk',
      mode: 'dpp',
      dppDay: chosenDay,
      title: (chosenDay === 1) ? 'SBI Clerk Prelims DPP Day 1' : `SBI Clerk Prelims DPP Day ${chosenDay}`,
      timerMinutes: (chosenDay === 1 ? 40 : 20),
      candidateName: (state.currentUser && (state.currentUser.displayName || state.currentUser.email.split('@')[0])) || 'Candidate'
    };

    const englishQuestions = questions.filter(q => (q.sectionId || '').toLowerCase().includes('eng'));
    const quantQuestions = questions.filter(q => {
      const s = (q.sectionId || '').toLowerCase();
      return s.includes('quant') || s.includes('num') || s.includes('math');
    });
    const reasoningQuestions = questions.filter(q => (q.sectionId || '').toLowerCase().includes('reason'));

    const sectionList = [];
    if (englishQuestions.length) sectionList.push({ id: 'english', name: 'English Language', questions: englishQuestions });
    if (quantQuestions.length) sectionList.push({ id: 'quant', name: 'Numerical Ability', questions: quantQuestions });
    if (reasoningQuestions.length) sectionList.push({ id: 'reasoning', name: 'Reasoning Ability', questions: reasoningQuestions });
    if (!sectionList.length) {
      sectionList.push({ id: 'general', name: 'Numerical Ability', questions: questions });
    }

    state.sections = sectionList;
    state.allQuestions = sectionList.flatMap(s => s.questions);
    state.currentSectionIdx = 0;
    state.currentQuestionIdx = 0;
    state.selectedAnswers = {};
    state.questionStatus = {};
    state.questionTimeSpent = {};

    state.allQuestions.forEach(q => {
      state.questionStatus[q.id] = 'not_visited';
      state.questionTimeSpent[q.id] = 0;
    });

    if (solExamTitle) solExamTitle.textContent = state.activeSession.title;
    if (cbtExamTitle) cbtExamTitle.textContent = state.activeSession.title;
    if (resExamTitleDisplay) resExamTitleDisplay.textContent = state.activeSession.title;

    return true;
  } catch (err) {
    console.error('Error loading exam data:', err);
    return false;
  }
}

// Auto-fill OTP from URL query parameter (e.g. ?code=123456 or ?otp=123456) or debug views
window.addEventListener('DOMContentLoaded', async () => {
  const urlParams = new URLSearchParams(window.location.search);
  const codeParam = urlParams.get('code') || urlParams.get('otp') || urlParams.get('pin');
  
  if (codeParam && codeParam.length === 6) {
    codeParam.split('').forEach((d, i) => { if (digitInputs[i]) digitInputs[i].value = d; });
    checkCodeComplete();
    if (connectCodeBtn && !connectCodeBtn.disabled) {
      connectCodeBtn.click();
      return;
    }
  }

  const dayParam = urlParams.get('day') || urlParams.get('dppDay') || urlParams.get('dpp');
  const targetDay = dayParam ? parseInt(dayParam, 10) : 8;

  if (urlParams.get('solutions') === '1' || urlParams.get('demo') === '1') {
    const qNum = parseInt(urlParams.get('q') || '1', 10);
    const ok = await loadDemoExamData(targetDay);
    if (ok) {
      state.solCurrentQIdx = Math.max(0, Math.min(qNum - 1, state.allQuestions.length - 1));
      renderSolutionsScreen();
    }
  } else if (urlParams.get('cbt') === '1') {
    const ok = await loadDemoExamData(targetDay);
    if (ok) {
      startExamWithData({ 
        title: (targetDay === 1) ? 'SBI Clerk Prelims DPP Day 1' : `SBI Clerk Prelims DPP Day ${targetDay}`, 
        dppDay: targetDay,
        timerMinutes: (targetDay === 1 ? 40 : 20) 
      }, 'sbi_clerk');
    }
  }
});
