/**
 * Target Bank Exam — PC Web CBT Portal
 * Complete Client-Side Application Logic (100% Free - Firebase Spark + GitHub Pages)
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
  questions: [],
  currentIndex: 0,
  selectedAnswers: {}, // { [questionId]: optionIndex }
  questionStatus: {},  // { [questionId]: 'not_visited' | 'not_answered' | 'answered' | 'marked' | 'marked_answered' }
  timerInterval: null,
  remainingSeconds: 1200,
  totalTimerSeconds: 1200,
  currentLanguage: 'en',
  examResult: null,
  activeFilter: 'all'
};

// DOM Elements
const authScreen = document.getElementById('authScreen');
const pairingScreen = document.getElementById('pairingScreen');
const cbtScreen = document.getElementById('cbtScreen');
const resultsScreen = document.getElementById('resultsScreen');

const userBadge = document.getElementById('userBadge');
const userName = document.getElementById('userName');
const userAvatar = document.getElementById('userAvatar');
const signOutBtn = document.getElementById('signOutBtn');

const googleSignInBtn = document.getElementById('googleSignInBtn');
const emailAuthForm = document.getElementById('emailAuthForm');
const toggleAuthMode = document.getElementById('toggleAuthMode');
const authTogglePrompt = document.getElementById('authTogglePrompt');
const submitAuthBtn = document.getElementById('submitAuthBtn');
const nameGroup = document.getElementById('nameGroup');
const authAlert = document.getElementById('authAlert');

const pairingAlert = document.getElementById('pairingAlert');
const digitInputs = [
  document.getElementById('digit1'),
  document.getElementById('digit2'),
  document.getElementById('digit3'),
  document.getElementById('digit4'),
  document.getElementById('digit5'),
  document.getElementById('digit6')
];
const connectCodeBtn = document.getElementById('connectCodeBtn');

// CBT Elements
const cbtExamTitle = document.getElementById('cbtExamTitle');
const cbtLangSelect = document.getElementById('cbtLangSelect');
const cbtTimerDisplay = document.getElementById('cbtTimerDisplay');
const cbtTimerBadge = document.getElementById('cbtTimerBadge');
const cbtSectionsBar = document.getElementById('cbtSectionsBar');
const cbtQuestionNumberLabel = document.getElementById('cbtQuestionNumberLabel');
const cbtQuestionText = document.getElementById('cbtQuestionText');
const cbtQuestionImages = document.getElementById('cbtQuestionImages');
const cbtOptionsList = document.getElementById('cbtOptionsList');
const cbtCandidateName = document.getElementById('cbtCandidateName');
const cbtCandidateId = document.getElementById('cbtCandidateId');
const cbtCandidatePhoto = document.getElementById('cbtCandidatePhoto');
const cbtPaletteGrid = document.getElementById('cbtPaletteGrid');

// CBT Counters
const countAnswered = document.getElementById('countAnswered');
const countNotAnswered = document.getElementById('countNotAnswered');
const countNotVisited = document.getElementById('countNotVisited');
const countMarked = document.getElementById('countMarked');
const countMarkedAnswered = document.getElementById('countMarkedAnswered');

// CBT Buttons
const btnMarkReview = document.getElementById('btnMarkReview');
const btnClearResponse = document.getElementById('btnClearResponse');
const btnPrevious = document.getElementById('btnPrevious');
const btnSaveNext = document.getElementById('btnSaveNext');
const btnSubmitTest = document.getElementById('btnSubmitTest');

// Modal Elements
const submitModal = document.getElementById('submitModal');
const btnCancelSubmit = document.getElementById('btnCancelSubmit');
const btnConfirmSubmit = document.getElementById('btnConfirmSubmit');
const modalAnswered = document.getElementById('modalAnswered');
const modalNotAnswered = document.getElementById('modalNotAnswered');
const modalMarked = document.getElementById('modalMarked');
const modalNotVisited = document.getElementById('modalNotVisited');

// Lightbox Elements
const lightboxModal = document.getElementById('lightboxModal');
const lightboxImg = document.getElementById('lightboxImg');

// Result Elements
const resScore = document.getElementById('resScore');
const resAccuracy = document.getElementById('resAccuracy');
const resTime = document.getElementById('resTime');
const resCorrect = document.getElementById('resCorrect');
const resIncorrect = document.getElementById('resIncorrect');
const solutionsList = document.getElementById('solutionsList');
const btnBackToHome = document.getElementById('btnBackToHome');

let isSignUpMode = false;

// ==========================================
// 2. Navigation & UI Helpers
// ==========================================
function showScreen(screen) {
  [authScreen, pairingScreen, cbtScreen, resultsScreen].forEach(s => s.classList.remove('active'));
  screen.classList.add('active');
  window.scrollTo(0, 0);
}

function showAlert(element, message, type = 'error') {
  element.textContent = message;
  element.className = `status-alert ${type}`;
  element.style.display = 'block';
}

function hideAlert(element) {
  element.style.display = 'none';
}

// Drive image conversion: converts share links to direct CDN
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

// LaTeX rendering with KaTeX
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
    console.warn('KaTeX rendering notice:', e);
  }
}

// Formats text with inline [img1], [img2] diagram tags
function formatTextWithImages(text, images) {
  if (!text) return '';
  const validImages = (images || []).map(convertDriveLink).filter(Boolean);

  let formatted = text.replace(/\[img(\d+)\]/gi, (match, p1) => {
    const idx = parseInt(p1, 10) - 1;
    if (idx >= 0 && idx < validImages.length) {
      return `<div class="question-image-wrapper">
        <img src="${validImages[idx]}" alt="Diagram ${p1}" onclick="openLightbox('${validImages[idx]}')">
      </div>`;
    }
    return '';
  });

  return formatted.replace(/\n/g, '<br>');
}

// Lightbox
window.openLightbox = function(url) {
  lightboxImg.src = url;
  lightboxModal.classList.add('active');
};
lightboxModal.addEventListener('click', () => {
  lightboxModal.classList.remove('active');
});

// ==========================================
// 3. Authentication Management
// ==========================================
auth.onAuthStateChanged((user) => {
  state.currentUser = user;
  if (user) {
    userName.textContent = user.displayName || user.email.split('@')[0];
    if (user.photoURL) {
      userAvatar.src = user.photoURL;
      userAvatar.style.display = 'block';
    } else {
      userAvatar.style.display = 'none';
    }
    userBadge.style.display = 'flex';
    
    // Save token to localStorage to remember PC
    localStorage.setItem('target_bank_exam_pc_user', user.uid);
    
    // If on auth screen, transition to code pairing
    if (authScreen.classList.contains('active')) {
      showScreen(pairingScreen);
      digitInputs[0].focus();
    }
  } else {
    userBadge.style.display = 'none';
    localStorage.removeItem('target_bank_exam_pc_user');
    showScreen(authScreen);
  }
});

// Google Sign-In
googleSignInBtn.addEventListener('click', async () => {
  hideAlert(authAlert);
  try {
    const provider = new firebase.auth.GoogleAuthProvider();
    await auth.signInWithPopup(provider);
  } catch (error) {
    console.error('Google Sign In Error:', error);
    showAlert(authAlert, error.message || 'Failed to sign in with Google');
  }
});

// Auth Mode Toggle
toggleAuthMode.addEventListener('click', () => {
  isSignUpMode = !isSignUpMode;
  nameGroup.style.display = isSignUpMode ? 'block' : 'none';
  submitAuthBtn.textContent = isSignUpMode ? 'Sign Up' : 'Sign In';
  authTogglePrompt.textContent = isSignUpMode ? 'Already have an account?' : "Don't have an account?";
  toggleAuthMode.textContent = isSignUpMode ? 'Sign In' : 'Sign Up';
  hideAlert(authAlert);
});

// Email & Password Auth
emailAuthForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideAlert(authAlert);
  
  const email = document.getElementById('authEmail').value.trim();
  const password = document.getElementById('authPassword').value;
  const name = document.getElementById('authName').value.trim();

  if (!email || !password) {
    showAlert(authAlert, 'Please enter email and password');
    return;
  }

  try {
    submitAuthBtn.disabled = true;
    submitAuthBtn.textContent = 'Please wait...';

    if (isSignUpMode) {
      const cred = await auth.createUserWithEmailAndPassword(email, password);
      if (name && cred.user) {
        await cred.user.updateProfile({ displayName: name });
      }
    } else {
      await auth.signInWithEmailAndPassword(email, password);
    }
  } catch (error) {
    console.error('Auth Error:', error);
    showAlert(authAlert, error.message || 'Authentication failed');
  } finally {
    submitAuthBtn.disabled = false;
    submitAuthBtn.textContent = isSignUpMode ? 'Sign Up' : 'Sign In';
  }
});

// Sign Out
signOutBtn.addEventListener('click', async () => {
  if (state.timerInterval) {
    if (!confirm('Are you sure you want to log out and exit the active exam?')) return;
    clearInterval(state.timerInterval);
  }
  await auth.signOut();
});

// ==========================================
// 4. 6-Digit Code Pairing Logic
// ==========================================
digitInputs.forEach((input, index) => {
  input.addEventListener('input', (e) => {
    const val = e.target.value.replace(/[^0-9]/g, '');
    e.target.value = val;

    if (val && index < digitInputs.length - 1) {
      digitInputs[index + 1].focus();
    }
    checkCodeComplete();
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Backspace' && !input.value && index > 0) {
      digitInputs[index - 1].focus();
    }
  });

  input.addEventListener('paste', (e) => {
    e.preventDefault();
    const pasteData = (e.clipboardData || window.clipboardData).getData('text');
    const digits = pasteData.replace(/[^0-9]/g, '').slice(0, 6);
    if (digits.length) {
      digits.split('').forEach((d, i) => {
        if (digitInputs[i]) digitInputs[i].value = d;
      });
      if (digits.length === 6) {
        digitInputs[5].focus();
      } else {
        digitInputs[digits.length].focus();
      }
      checkCodeComplete();
    }
  });
});

function getEnteredCode() {
  return digitInputs.map(input => input.value).join('');
}

function checkCodeComplete() {
  const code = getEnteredCode();
  connectCodeBtn.disabled = code.length !== 6;
}

connectCodeBtn.addEventListener('click', async () => {
  const code = getEnteredCode();
  if (code.length !== 6) return;

  hideAlert(pairingAlert);
  connectCodeBtn.disabled = true;
  connectCodeBtn.textContent = 'Verifying Code...';

  try {
    const sessionDoc = await db.collection('pc_sessions').doc(code).get();

    if (!sessionDoc.exists) {
      showAlert(pairingAlert, 'Invalid code. Please check the code on your phone and try again.');
      connectCodeBtn.disabled = false;
      connectCodeBtn.textContent = 'Start Test on PC';
      return;
    }

    const sessionData = sessionDoc.data();

    // Check expiration
    if (sessionData.expiresAt && Date.now() > sessionData.expiresAt) {
      showAlert(pairingAlert, 'This code has expired. Please generate a new code on your phone.');
      connectCodeBtn.disabled = false;
      connectCodeBtn.textContent = 'Start Test on PC';
      return;
    }

    if (sessionData.status === 'completed') {
      showAlert(pairingAlert, 'This test has already been completed.');
      connectCodeBtn.disabled = false;
      connectCodeBtn.textContent = 'Start Test on PC';
      return;
    }

    // Connect session
    state.activeSession = sessionData;
    state.sessionCode = code;

    // Update session status in Firestore
    await db.collection('pc_sessions').doc(code).update({
      status: 'connected',
      connectedAt: Date.now(),
      connectedUserEmail: state.currentUser ? state.currentUser.email : sessionData.userEmail
    });

    // Load exam data
    await loadExamData(sessionData);

  } catch (error) {
    console.error('Pairing error:', error);
    showAlert(pairingAlert, 'Error connecting: ' + error.message);
    connectCodeBtn.disabled = false;
    connectCodeBtn.textContent = 'Start Test on PC';
  }
});

// ==========================================
// 5. Exam Data Loading
// ==========================================
async function loadExamData(session) {
  const examId = session.examId || 'sbi_clerk';
  try {
    const response = await fetch(`data/${examId}.json`);
    if (!response.ok) {
      throw new Error(`Could not load test data for ${examId}`);
    }
    const examJson = await response.json();

    // Filter questions based on mode
    let questions = [];
    if (session.mode === 'dpp' && session.dppDay) {
      questions = (examJson.questions || []).filter(q => q.type === 'dpp' && q.dppDay === session.dppDay);
      
      // Fallback: if dppDay has no questions in JSON, take first 20 prelims questions
      if (questions.length === 0) {
        questions = (examJson.questions || []).slice(0, 20);
      }
    } else if (session.sectionId) {
      questions = (examJson.questions || []).filter(q => q.sectionId === session.sectionId);
    } else {
      questions = examJson.questions || [];
    }

    if (!questions.length) {
      throw new Error('No questions found for this test session.');
    }

    state.questions = questions;
    state.currentIndex = 0;
    state.selectedAnswers = {};
    state.questionStatus = {};

    // Determine timer
    let timerMinutes = session.timerMinutes || 20;
    if (session.mode === 'dpp' && examJson.dppMeta) {
      const meta = examJson.dppMeta.find(m => m.day === session.dppDay);
      if (meta && meta.timerMinutes) {
        timerMinutes = meta.timerMinutes;
      }
    }
    state.remainingSeconds = timerMinutes * 60;
    state.totalTimerSeconds = state.remainingSeconds;

    // Initialize statuses: first question is 'not_answered', others 'not_visited'
    state.questions.forEach((q, idx) => {
      state.questionStatus[q.id] = idx === 0 ? 'not_answered' : 'not_visited';
    });

    startCbtExam(session);

  } catch (error) {
    console.error('Data loading error:', error);
    showAlert(pairingAlert, 'Failed to load test questions: ' + error.message);
    connectCodeBtn.disabled = false;
    connectCodeBtn.textContent = 'Start Test on PC';
  }
}

// ==========================================
// 6. CBT Exam Engine
// ==========================================
function startCbtExam(session) {
  showScreen(cbtScreen);

  // Setup Header & Info
  const examTitle = session.title || `${(session.examId || 'Banking').replace('_', ' ').toUpperCase()} Test`;
  cbtExamTitle.textContent = examTitle;
  
  const cName = (state.currentUser && (state.currentUser.displayName || state.currentUser.email.split('@')[0])) 
    || session.candidateName || 'Candidate';
  cbtCandidateName.textContent = cName;
  cbtCandidateId.textContent = `UID: ${(state.currentUser ? state.currentUser.uid.slice(0, 8) : 'GUEST').toUpperCase()}`;
  cbtCandidatePhoto.textContent = cName.charAt(0).toUpperCase();

  // Populate Section Tabs
  buildSectionTabs();

  // Build Palette Buttons
  buildPaletteGrid();

  // Render first question
  renderCurrentQuestion();

  // Start Timer
  startTimer();
}

function buildSectionTabs() {
  cbtSectionsBar.innerHTML = '';
  // Unique sections in current questions
  const sections = Array.from(new Set(state.questions.map(q => q.sectionId || 'General')));

  sections.forEach((sec, idx) => {
    const tab = document.createElement('div');
    tab.className = `cbt-section-tab ${idx === 0 ? 'active' : ''}`;
    tab.textContent = formatSectionName(sec);
    tab.onclick = () => {
      // Find first question of this section
      const targetIdx = state.questions.findIndex(q => (q.sectionId || 'General') === sec);
      if (targetIdx !== -1) {
        navigateToQuestion(targetIdx);
      }
    };
    cbtSectionsBar.appendChild(tab);
  });
}

function formatSectionName(sec) {
  const lower = sec.toLowerCase();
  if (lower.includes('quant') || lower.includes('math')) return 'Quantitative Aptitude';
  if (lower.includes('reason')) return 'Reasoning Ability';
  if (lower.includes('eng')) return 'English Language';
  if (lower.includes('ga') || lower.includes('aware')) return 'General Awareness';
  return sec.charAt(0).toUpperCase() + sec.slice(1);
}

function updateActiveSectionTab() {
  const currentQ = state.questions[state.currentIndex];
  const currentSec = currentQ.sectionId || 'General';
  const tabs = cbtSectionsBar.querySelectorAll('.cbt-section-tab');
  tabs.forEach(tab => {
    if (tab.textContent === formatSectionName(currentSec)) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });
}

function buildPaletteGrid() {
  cbtPaletteGrid.innerHTML = '';
  state.questions.forEach((q, idx) => {
    const btn = document.createElement('button');
    btn.className = 'palette-btn status-not-visited';
    btn.id = `paletteBtn_${idx}`;
    btn.textContent = idx + 1;
    btn.onclick = () => navigateToQuestion(idx);
    cbtPaletteGrid.appendChild(btn);
  });
  updatePaletteUI();
}

function updatePaletteUI() {
  let ans = 0, notAns = 0, notVis = 0, mrk = 0, mrkAns = 0;

  state.questions.forEach((q, idx) => {
    const btn = document.getElementById(`paletteBtn_${idx}`);
    if (!btn) return;

    const status = state.questionStatus[q.id] || 'not_visited';
    btn.className = `palette-btn status-${status.replace('_', '-')}`;
    if (idx === state.currentIndex) {
      btn.classList.add('current');
    }

    if (status === 'answered') ans++;
    else if (status === 'not_answered') notAns++;
    else if (status === 'not_visited') notVis++;
    else if (status === 'marked') mrk++;
    else if (status === 'marked_answered') mrkAns++;
  });

  countAnswered.textContent = ans;
  countNotAnswered.textContent = notAns;
  countNotVisited.textContent = notVis;
  countMarked.textContent = mrk;
  countMarkedAnswered.textContent = mrkAns;
}

function renderCurrentQuestion() {
  const q = state.questions[state.currentIndex];
  if (!q) return;

  cbtQuestionNumberLabel.textContent = `Question No. ${state.currentIndex + 1} of ${state.questions.length}`;

  const lang = state.currentLanguage;
  const isHi = lang === 'hi';

  // Text
  const rawText = (isHi && q.questionTextHi) ? q.questionTextHi : q.questionText;
  const images = (isHi && q.questionImagesHi && q.questionImagesHi.length) 
    ? q.questionImagesHi 
    : (q.questionImages || (q.questionImageDriveLink ? [q.questionImageDriveLink] : []));

  cbtQuestionText.innerHTML = formatTextWithImages(rawText, images);
  renderMath(cbtQuestionText);

  // Options
  const rawOptions = (isHi && q.optionsHi && q.optionsHi.length) ? q.optionsHi : q.options;
  const optionLetters = ['A', 'B', 'C', 'D', 'E', 'F'];
  const selectedIndex = state.selectedAnswers[q.id];

  cbtOptionsList.innerHTML = '';
  rawOptions.forEach((optText, optIdx) => {
    const item = document.createElement('div');
    item.className = `option-item ${selectedIndex === optIdx ? 'selected' : ''}`;
    item.onclick = () => selectOption(optIdx);

    item.innerHTML = `
      <div class="option-radio">
        <div class="option-radio-dot"></div>
      </div>
      <div class="option-label">${optionLetters[optIdx]}.</div>
      <div class="option-content">${optText}</div>
    `;
    renderMath(item.querySelector('.option-content'));
    cbtOptionsList.appendChild(item);
  });

  updateActiveSectionTab();
  updatePaletteUI();
}

function selectOption(index) {
  const q = state.questions[state.currentIndex];
  state.selectedAnswers[q.id] = index;

  // If marked, change to marked_answered, else answered
  const curStatus = state.questionStatus[q.id];
  if (curStatus === 'marked' || curStatus === 'marked_answered') {
    state.questionStatus[q.id] = 'marked_answered';
  } else {
    state.questionStatus[q.id] = 'answered';
  }

  renderCurrentQuestion();
}

function navigateToQuestion(newIndex) {
  if (newIndex < 0 || newIndex >= state.questions.length) return;

  const currentQ = state.questions[state.currentIndex];
  // If moving away and current question is not visited, mark as not answered
  if (state.questionStatus[currentQ.id] === 'not_visited') {
    state.questionStatus[currentQ.id] = 'not_answered';
  }

  state.currentIndex = newIndex;
  const newQ = state.questions[newIndex];
  if (state.questionStatus[newQ.id] === 'not_visited') {
    state.questionStatus[newQ.id] = 'not_answered';
  }

  renderCurrentQuestion();
}

// Action Button Listeners
btnSaveNext.addEventListener('click', () => {
  const q = state.questions[state.currentIndex];
  const hasAns = state.selectedAnswers[q.id] !== undefined;

  if (hasAns) {
    state.questionStatus[q.id] = 'answered';
  } else {
    state.questionStatus[q.id] = 'not_answered';
  }

  if (state.currentIndex < state.questions.length - 1) {
    navigateToQuestion(state.currentIndex + 1);
  } else {
    updatePaletteUI();
  }
});

btnMarkReview.addEventListener('click', () => {
  const q = state.questions[state.currentIndex];
  const hasAns = state.selectedAnswers[q.id] !== undefined;

  state.questionStatus[q.id] = hasAns ? 'marked_answered' : 'marked';

  if (state.currentIndex < state.questions.length - 1) {
    navigateToQuestion(state.currentIndex + 1);
  } else {
    updatePaletteUI();
  }
});

btnClearResponse.addEventListener('click', () => {
  const q = state.questions[state.currentIndex];
  delete state.selectedAnswers[q.id];
  state.questionStatus[q.id] = 'not_answered';
  renderCurrentQuestion();
});

btnPrevious.addEventListener('click', () => {
  if (state.currentIndex > 0) {
    navigateToQuestion(state.currentIndex - 1);
  }
});

cbtLangSelect.addEventListener('change', (e) => {
  state.currentLanguage = e.target.value;
  renderCurrentQuestion();
});

// Timer Logic
function startTimer() {
  if (state.timerInterval) clearInterval(state.timerInterval);

  updateTimerDisplay();

  state.timerInterval = setInterval(() => {
    state.remainingSeconds--;
    updateTimerDisplay();

    if (state.remainingSeconds <= 0) {
      clearInterval(state.timerInterval);
      alert('Time is up! Submitting your test automatically.');
      finalizeSubmission();
    }
  }, 1000);
}

function updateTimerDisplay() {
  const m = Math.floor(state.remainingSeconds / 60);
  const s = state.remainingSeconds % 60;
  const formatted = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  cbtTimerDisplay.textContent = formatted;

  if (state.remainingSeconds < 60) {
    cbtTimerBadge.className = 'cbt-timer-badge danger';
  } else if (state.remainingSeconds < 300) {
    cbtTimerBadge.className = 'cbt-timer-badge warning';
  } else {
    cbtTimerBadge.className = 'cbt-timer-badge';
  }
}

// ==========================================
// 7. Test Submission & Score Calculation
// ==========================================
btnSubmitTest.addEventListener('click', () => {
  // Populate Confirmation Modal
  let ans = 0, notAns = 0, mrk = 0, notVis = 0;
  state.questions.forEach(q => {
    const s = state.questionStatus[q.id] || 'not_visited';
    if (s === 'answered' || s === 'marked_answered') ans++;
    else if (s === 'not_answered') notAns++;
    else if (s === 'marked') mrk++;
    else notVis++;
  });

  modalAnswered.textContent = ans;
  modalNotAnswered.textContent = notAns;
  modalMarked.textContent = mrk;
  modalNotVisited.textContent = notVis;

  submitModal.classList.add('active');
});

btnCancelSubmit.addEventListener('click', () => {
  submitModal.classList.remove('active');
});

btnConfirmSubmit.addEventListener('click', () => {
  submitModal.classList.remove('active');
  finalizeSubmission();
});

async function finalizeSubmission() {
  if (state.timerInterval) clearInterval(state.timerInterval);

  let correctCount = 0;
  let incorrectCount = 0;
  let unattemptedCount = 0;

  state.questions.forEach(q => {
    const selected = state.selectedAnswers[q.id];
    if (selected === undefined) {
      unattemptedCount++;
    } else if (selected === q.correctIndex) {
      correctCount++;
    } else {
      incorrectCount++;
    }
  });

  const totalQuestions = state.questions.length;
  const answeredCount = correctCount + incorrectCount;
  // Banking Standard: +1.00 for correct, -0.25 for incorrect
  const rawScore = (correctCount * 1.0) - (incorrectCount * 0.25);
  const score = Math.max(0, Math.round(rawScore * 100) / 100);
  const accuracy = answeredCount > 0 ? Math.round((correctCount / answeredCount) * 100) : 0;
  const timeTakenSeconds = Math.max(1, state.totalTimerSeconds - state.remainingSeconds);

  const completedAt = new Date().toISOString();
  const userId = state.currentUser ? state.currentUser.uid : (state.activeSession.userId || 'guest_user');
  const candidateName = state.currentUser 
    ? (state.currentUser.displayName || state.currentUser.email.split('@')[0]) 
    : (state.activeSession.candidateName || 'Candidate');
  const examId = state.activeSession.examId || 'sbi_clerk';
  const dppDay = state.activeSession.dppDay;

  const resultPayload = {
    score,
    maxScore: totalQuestions * 1.0,
    totalQuestions,
    answeredCount,
    notAnsweredCount: unattemptedCount,
    correctCount,
    incorrectCount,
    unattemptedCount,
    accuracy,
    timeTakenSeconds,
    completedAt,
    answers: state.selectedAnswers
  };

  state.examResult = resultPayload;

  // 1. Sync submission to Firestore
  try {
    // Update pc_session status to "completed"
    if (state.sessionCode) {
      await db.collection('pc_sessions').doc(state.sessionCode).update({
        status: 'completed',
        result: resultPayload,
        completedAt: Date.now()
      });
    }

    // If DPP session, write to dpp_submissions and dpp_leaderboards
    if (dppDay !== undefined && dppDay !== null) {
      const submissionKey = `${userId}_${examId}_dpp_${dppDay}`;
      const istDate = getIstDateKey();

      const dppSubmissionData = {
        userId,
        candidateName,
        examId,
        dppDay,
        score,
        totalQuestions,
        timeTakenSeconds,
        istDate,
        submittedAt: completedAt
      };

      await db.collection('dpp_submissions').doc(submissionKey).set(dppSubmissionData, { merge: true });

      // Update exam leaderboard doc
      await updateFirestoreLeaderboardDoc(
        `${examId}_${userId}`,
        userId,
        candidateName,
        examId,
        score,
        timeTakenSeconds,
        completedAt
      );

      // Update all-exams global leaderboard doc
      await updateFirestoreLeaderboardDoc(
        `all_${userId}`,
        userId,
        candidateName,
        'all',
        score,
        timeTakenSeconds,
        completedAt
      );
    }
  } catch (syncErr) {
    console.warn('Firestore sync warning:', syncErr);
  }

  // Display Scorecard & Solutions
  displayResultsScreen();
}

function getIstDateKey() {
  const now = new Date();
  const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
  const ist = new Date(utc + (3600000 * 5.5));
  const y = ist.getFullYear();
  const m = String(ist.getMonth() + 1).padStart(2, '0');
  const d = String(ist.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

async function updateFirestoreLeaderboardDoc(docId, userId, candidateName, examId, score, timeSeconds, nowIso) {
  const docRef = db.collection('dpp_leaderboards').doc(docId);
  try {
    const snap = await docRef.get();
    if (!snap.exists) {
      await docRef.set({
        userId,
        candidateName,
        examId,
        dppsAttempted: 1,
        totalScore: score,
        averageScore: score,
        totalTimeSeconds: timeSeconds,
        averageTimeSeconds: timeSeconds,
        lastSubmittedAt: nowIso
      });
    } else {
      const data = snap.data();
      const currentDpps = data.dppsAttempted || 0;
      const currentTotalScore = data.totalScore || 0;
      const currentTotalTime = data.totalTimeSeconds || 0;

      const newDpps = currentDpps + 1;
      const newTotalScore = currentTotalScore + score;
      const newTotalTime = currentTotalTime + timeSeconds;

      await docRef.update({
        candidateName,
        dppsAttempted: newDpps,
        totalScore: newTotalScore,
        averageScore: newTotalScore / newDpps,
        totalTimeSeconds: newTotalTime,
        averageTimeSeconds: newTotalTime / newDpps,
        lastSubmittedAt: nowIso
      });
    }
  } catch (e) {
    console.warn('Leaderboard update notice:', e);
  }
}

// ==========================================
// 8. Results & Solutions Screen
// ==========================================
function displayResultsScreen() {
  showScreen(resultsScreen);

  const res = state.examResult;
  resScore.textContent = `${res.score.toFixed(2)} / ${res.maxScore.toFixed(0)}`;
  resAccuracy.textContent = `${res.accuracy}%`;
  
  const m = Math.floor(res.timeTakenSeconds / 60);
  const s = res.timeTakenSeconds % 60;
  resTime.textContent = `${m}m ${s}s`;

  resCorrect.textContent = res.correctCount;
  resIncorrect.textContent = res.incorrectCount;

  // Filter counters
  document.getElementById('cntFilterAll').textContent = state.questions.length;
  document.getElementById('cntFilterCorrect').textContent = res.correctCount;
  document.getElementById('cntFilterIncorrect').textContent = res.incorrectCount;
  document.getElementById('cntFilterUnattempted').textContent = res.unattemptedCount;

  renderSolutions();
}

// Filter button handlers
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.activeFilter = btn.dataset.filter;
    renderSolutions();
  });
});

function renderSolutions() {
  solutionsList.innerHTML = '';
  const filter = state.activeFilter;
  const isHi = state.currentLanguage === 'hi';
  const optionLetters = ['A', 'B', 'C', 'D', 'E', 'F'];

  state.questions.forEach((q, idx) => {
    const selectedIdx = state.selectedAnswers[q.id];
    const isAttempted = selectedIdx !== undefined;
    const isCorrect = isAttempted && selectedIdx === q.correctIndex;
    const isIncorrect = isAttempted && !isCorrect;

    if (filter === 'correct' && !isCorrect) return;
    if (filter === 'incorrect' && !isIncorrect) return;
    if (filter === 'unattempted' && isAttempted) return;

    let chipClass = 'sol-chip-unattempted';
    let chipText = 'Skipped';
    if (isCorrect) {
      chipClass = 'sol-chip-correct';
      chipText = 'Correct (+1.00)';
    } else if (isIncorrect) {
      chipClass = 'sol-chip-incorrect';
      chipText = 'Incorrect (-0.25)';
    }

    const item = document.createElement('div');
    item.className = 'solution-item';

    const qText = (isHi && q.questionTextHi) ? q.questionTextHi : q.questionText;
    const qImages = (isHi && q.questionImagesHi && q.questionImagesHi.length) 
      ? q.questionImagesHi 
      : (q.questionImages || (q.questionImageDriveLink ? [q.questionImageDriveLink] : []));

    const options = (isHi && q.optionsHi && q.optionsHi.length) ? q.optionsHi : q.options;

    const explanationText = (isHi && q.explanationHi) ? q.explanationHi : (q.explanation || 'No detailed explanation provided.');
    const explanationImages = (isHi && q.explanationImagesHi && q.explanationImagesHi.length)
      ? q.explanationImagesHi
      : (q.explanationImages || (q.explanationImageDriveLink ? [q.explanationImageDriveLink] : []));

    let optionsHtml = '';
    options.forEach((opt, oIdx) => {
      let optClass = '';
      let badge = '';

      if (oIdx === q.correctIndex) {
        optClass = 'border: 2px solid #2e7d32; background: #e8f5e9; font-weight: 600;';
        badge = '<span style="color: #2e7d32; font-weight: 700; margin-left: 8px;">✓ Correct Option</span>';
      } else if (oIdx === selectedIdx) {
        optClass = 'border: 2px solid #c62828; background: #ffebee; font-weight: 600;';
        badge = '<span style="color: #c62828; font-weight: 700; margin-left: 8px;">✗ Your Choice</span>';
      }

      optionsHtml += `
        <div style="padding: 10px 14px; margin-bottom: 8px; border-radius: 6px; ${optClass || 'border: 1px solid #e0e0e0; background: white;'}">
          <strong>${optionLetters[oIdx]}.</strong> <span class="math-content">${opt}</span> ${badge}
        </div>
      `;
    });

    item.innerHTML = `
      <div class="sol-item-header">
        <span style="font-weight: 700; font-size: 15px;">Question ${idx + 1}</span>
        <span class="sol-status-chip ${chipClass}">${chipText}</span>
      </div>
      <div class="question-text" style="margin-bottom: 16px;">
        ${formatTextWithImages(qText, qImages)}
      </div>
      <div style="margin-bottom: 16px;">
        ${optionsHtml}
      </div>
      <div class="sol-explanation-box">
        <div class="sol-explanation-title">💡 Step-by-Step Explanation:</div>
        <div>${formatTextWithImages(explanationText, explanationImages)}</div>
      </div>
    `;

    renderMath(item);
    solutionsList.appendChild(item);
  });

  if (!solutionsList.children.length) {
    solutionsList.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 32px;">No questions match this filter.</div>';
  }
}

btnBackToHome.addEventListener('click', () => {
  digitInputs.forEach(input => input.value = '');
  connectCodeBtn.disabled = true;
  connectCodeBtn.textContent = 'Start Test on PC';
  showScreen(pairingScreen);
  digitInputs[0].focus();
});
