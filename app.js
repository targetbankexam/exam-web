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

// Result Screen Elements (Photo 5)
const resScoreText = document.getElementById('resScoreText');
const resCutoffText = document.getElementById('resCutoffText');
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
const btnGoToSolutions = document.getElementById('btnGoToSolutions');

// Solutions Screen Elements
const toggleReattemptMode = document.getElementById('toggleReattemptMode');
const btnBackToResultSummary = document.getElementById('btnBackToResultSummary');
const solQNumberLabel = document.getElementById('solQNumberLabel');
const solSectionLabel = document.getElementById('solSectionLabel');
const solQTimeSpent = document.getElementById('solQTimeSpent');
const solStatusTag = document.getElementById('solStatusTag');
const solQuestionText = document.getElementById('solQuestionText');
const solQuestionImages = document.getElementById('solQuestionImages');
const solOptionsGroup = document.getElementById('solOptionsGroup');
const reattemptActionBox = document.getElementById('reattemptActionBox');
const btnCheckReattemptAnswer = document.getElementById('btnCheckReattemptAnswer');
const solExplanationBox = document.getElementById('solExplanationBox');
const solExplanationText = document.getElementById('solExplanationText');
const solExplanationImages = document.getElementById('solExplanationImages');
const solPaletteGrid = document.getElementById('solPaletteGrid');

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

  let formatted = text.replace(/\[img(\d+)\]/gi, (match, p1) => {
    const idx = parseInt(p1, 10) - 1;
    if (idx >= 0 && idx < validImages.length) {
      return `<div style="margin: 12px 0;"><img src="${validImages[idx]}" alt="Diagram" style="max-width: 100%; max-height: 320px; border-radius: 6px; cursor: zoom-in;" onclick="openLightbox('${validImages[idx]}')"></div>`;
    }
    return '';
  });

  return formatted.replace(/\n/g, '<br>');
}

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
    const name = user.displayName || user.email.split('@')[0];
    userName.textContent = name;
    if (user.photoURL) {
      userAvatar.src = user.photoURL;
      userAvatar.style.display = 'block';
    }
    userBadge.style.display = 'flex';
    localStorage.setItem('target_bank_exam_pc_user', user.uid);

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

document.getElementById('googleSignInBtn').addEventListener('click', async () => {
  try {
    const provider = new firebase.auth.GoogleAuthProvider();
    await auth.signInWithPopup(provider);
  } catch (err) {
    showAlert(document.getElementById('authAlert'), err.message || 'Google sign in failed');
  }
});

signOutBtn.addEventListener('click', () => auth.signOut());

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
  const response = await fetch(`data/${examId}.json`);
  if (!response.ok) throw new Error(`Could not load questions for ${examId}`);
  const examJson = await response.json();

  let questions = [];
  if (session.mode === 'dpp' && session.dppDay) {
    questions = (examJson.questions || []).filter(q => q.type === 'dpp' && q.dppDay === session.dppDay);
    if (!questions.length) {
      questions = (examJson.questions || []).slice(0, 35);
    }
  } else {
    questions = examJson.questions || [];
  }

  state.allQuestions = questions;

  // Organize questions strictly in specified order:
  // 1. Quant / Numerical Ability, 2. Reasoning Ability, 3. English Language
  const quantQuestions = questions.filter(q => {
    const s = (q.sectionId || '').toLowerCase();
    return s.includes('quant') || s.includes('num') || s.includes('math');
  });

  const reasoningQuestions = questions.filter(q => {
    const s = (q.sectionId || '').toLowerCase();
    return s.includes('reason');
  });

  const englishQuestions = questions.filter(q => {
    const s = (q.sectionId || '').toLowerCase();
    return s.includes('eng');
  });

  // If questions don't have distinct sections, distribute or preserve
  const sectionList = [];
  if (quantQuestions.length || reasoningQuestions.length || englishQuestions.length) {
    if (quantQuestions.length) sectionList.push({ id: 'quant', name: 'Numerical Ability', questions: quantQuestions });
    if (reasoningQuestions.length) sectionList.push({ id: 'reasoning', name: 'Reasoning Ability', questions: reasoningQuestions });
    if (englishQuestions.length) sectionList.push({ id: 'english', name: 'English Language', questions: englishQuestions });
  } else {
    sectionList.push({ id: 'general', name: 'Numerical Ability', questions: questions });
  }

  state.sections = sectionList;
  state.currentSectionIdx = 0;
  state.currentQuestionIdx = 0;
  state.selectedAnswers = {};
  state.questionStatus = {};
  state.questionTimeSpent = {};

  questions.forEach(q => {
    state.questionStatus[q.id] = 'not_visited';
    state.questionTimeSpent[q.id] = 0;
  });

  // Populate Instructions Page 1 (Photo 1)
  const titleClean = (session.title || `${examId.toUpperCase()} Prelims Daily Practice Paper`)
    .replace(/mock test/gi, 'Daily Practice Paper')
    .replace(/test/gi, 'Examination');

  instTitle1.textContent = titleClean;
  instTitle2.textContent = titleClean;
  cbtExamTitle.textContent = titleClean;

  const totalMinutes = session.timerMinutes || 60;
  instTotalDuration.textContent = totalMinutes;
  instTotalQuestions.textContent = questions.length;

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
    const item = document.createElement('div');
    item.className = 'palette-item';
    item.id = `pal_q_${idx}`;
    item.textContent = idx + 1;
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

  cbtQuestionNumberLabel.textContent = `Q: ${state.currentQuestionIdx + 1} / ${currentSection.questions.length}`;

  const isHi = state.defaultLanguage === 'hi';
  const qText = (isHi && q.questionTextHi) ? q.questionTextHi : q.questionText;
  const qImages = (isHi && q.questionImagesHi && q.questionImagesHi.length) 
    ? q.questionImagesHi 
    : (q.questionImages || (q.questionImageDriveLink ? [q.questionImageDriveLink] : []));

  // Two-column layout check (Photos 3 & 4: study following information / comprehension)
  const isPassage = qText.length > 220 || qText.includes('Study the following') || qText.includes('In a certain code');
  if (isPassage && qText.includes('\n\n')) {
    const parts = qText.split('\n\n');
    cbtPassageCol.style.display = 'block';
    cbtPassageText.innerHTML = formatTextWithImages(parts[0], qImages);
    renderMath(cbtPassageText);

    cbtQuestionText.innerHTML = formatTextWithImages(parts.slice(1).join('\n\n'), []);
  } else {
    cbtPassageCol.style.display = 'none';
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

  resScoreText.textContent = score.toFixed(0);
  resCutoffText.textContent = '62'; // Standard cut-off range as shown in Photo 5

  resCardScore.textContent = `${score.toFixed(0)}/${totalQ}`;
  resCardAttempted.textContent = `${attempted}/${totalQ}`;
  resCardCorrect.textContent = `${correct}/${totalQ}`;
  resCardIncorrect.textContent = `${incorrect}/${totalQ}`;
  resCardSkipped.textContent = `${skipped}/${totalQ}`;
  resCardUnseen.textContent = `${unseen}/${totalQ}`;

  resCardAccuracy.textContent = `${accuracy}%`;

  function fmt(secs) {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  resCardTotalTime.textContent = fmt(totalTime);
  resCardUtilizedTime.textContent = fmt(utilizedTime);
  resCardWastedTime.textContent = fmt(wastedTime);
}

// View Solutions Button (ONLY this button as requested)
btnGoToSolutions.addEventListener('click', () => {
  state.solCurrentQIdx = 0;
  state.isReattemptMode = false;
  state.reattemptSelections = {};
  state.reattemptChecked = {};
  toggleReattemptMode.classList.remove('active');
  renderSolutionsScreen();
});

// ==========================================
// 8. Solutions & Reattempt Mode Screen
// ==========================================
function renderSolutionsScreen() {
  showScreen(solutionsScreen);
  buildSolutionsPalette();
  renderSolutionQuestion();
}

function buildSolutionsPalette() {
  solPaletteGrid.innerHTML = '';

  state.allQuestions.forEach((q, idx) => {
    const card = document.createElement('div');
    card.className = 'sol-palette-card';
    card.onclick = () => {
      state.solCurrentQIdx = idx;
      renderSolutionQuestion();
    };

    const chosen = state.selectedAnswers[q.id];
    let badgeClass = 'skipped';
    let icon = '-';

    if (chosen !== undefined) {
      if (chosen === q.correctIndex) {
        badgeClass = 'correct';
        icon = '✓';
      } else {
        badgeClass = 'wrong';
        icon = '✗';
      }
    }

    const timeSpent = state.questionTimeSpent[q.id] || 0;
    const timeLabel = timeSpent > 60 
      ? `${Math.floor(timeSpent/60)}m ${timeSpent%60}s` 
      : `${timeSpent}s`;

    card.innerHTML = `
      <div class="sol-badge ${badgeClass}">${idx + 1}</div>
      <div class="sol-q-time-label">${timeLabel}</div>
    `;

    solPaletteGrid.appendChild(card);
  });
}

function renderSolutionQuestion() {
  const q = state.allQuestions[state.solCurrentQIdx];
  if (!q) return;

  const isHi = state.defaultLanguage === 'hi';
  const qText = (isHi && q.questionTextHi) ? q.questionTextHi : q.questionText;
  const qImages = (isHi && q.questionImagesHi && q.questionImagesHi.length) 
    ? q.questionImagesHi 
    : (q.questionImages || (q.questionImageDriveLink ? [q.questionImageDriveLink] : []));

  solQNumberLabel.textContent = `Question ${state.solCurrentQIdx + 1}`;
  
  // Section name
  const secName = (q.sectionId || '').includes('quant') ? 'Numerical Ability' 
    : ((q.sectionId || '').includes('reason') ? 'Reasoning Ability' : 'English Language');
  solSectionLabel.textContent = `(${secName})`;

  const timeSpent = state.questionTimeSpent[q.id] || 0;
  solQTimeSpent.textContent = `⏱ Time Taken: ${timeSpent}s`;

  const chosenOpt = state.selectedAnswers[q.id];
  if (chosenOpt === undefined) {
    solStatusTag.className = 'sol-status-tag tag-skipped';
    solStatusTag.textContent = 'Skipped';
  } else if (chosenOpt === q.correctIndex) {
    solStatusTag.className = 'sol-status-tag tag-correct';
    solStatusTag.textContent = 'Correct (+1.00)';
  } else {
    solStatusTag.className = 'sol-status-tag tag-wrong';
    solStatusTag.textContent = 'Incorrect (-0.25)';
  }

  solQuestionText.innerHTML = formatTextWithImages(qText, qImages);
  renderMath(solQuestionText);

  // Options & Explanations Handling
  const options = (isHi && q.optionsHi && q.optionsHi.length) ? q.optionsHi : q.options;
  const letters = ['A', 'B', 'C', 'D', 'E', 'F'];
  solOptionsGroup.innerHTML = '';

  if (state.isReattemptMode) {
    // REATTEMPT MODE: Solutions & correct answers are HIDDEN!
    // Allows user to re-attempt the question
    const reChoice = state.reattemptSelections[q.id];
    const isChecked = state.reattemptChecked[q.id];

    options.forEach((optText, oIdx) => {
      const row = document.createElement('div');
      row.className = `cbt-opt-row ${reChoice === oIdx ? 'selected' : ''}`;
      row.onclick = () => {
        if (!isChecked) {
          state.reattemptSelections[q.id] = oIdx;
          renderSolutionQuestion();
        }
      };

      let badge = '';
      if (isChecked) {
        if (oIdx === q.correctIndex) {
          row.style.background = '#e8f5e9';
          row.style.border = '1.5px solid #2e7d32';
          badge = '<span style="color: #2e7d32; font-weight: 700; margin-left: 8px;">✓ Correct</span>';
        } else if (oIdx === reChoice) {
          row.style.background = '#ffebee';
          row.style.border = '1.5px solid #c62828';
          badge = '<span style="color: #c62828; font-weight: 700; margin-left: 8px;">✗ Your Choice</span>';
        }
      }

      row.innerHTML = `
        <div class="cbt-opt-radio">
          <div class="cbt-opt-radio-dot" style="${reChoice === oIdx ? 'display: block;' : ''}"></div>
        </div>
        <div class="cbt-opt-text"><strong>${letters[oIdx]})</strong> ${optText} ${badge}</div>
      `;
      renderMath(row.querySelector('.cbt-opt-text'));
      solOptionsGroup.appendChild(row);
    });

    reattemptActionBox.style.display = isChecked ? 'none' : 'block';
    solExplanationBox.style.display = isChecked ? 'block' : 'none';

  } else {
    // NORMAL SOLUTION MODE: Solution shown after question!
    reattemptActionBox.style.display = 'none';
    solExplanationBox.style.display = 'block';

    options.forEach((optText, oIdx) => {
      const row = document.createElement('div');
      row.className = 'cbt-opt-row';

      let extraBadge = '';
      if (oIdx === q.correctIndex) {
        row.style.background = '#e8f5e9';
        row.style.border = '1.5px solid #2e7d32';
        extraBadge = '<span style="color: #2e7d32; font-weight: 700; margin-left: 8px;">✓ Correct Option</span>';
      } else if (oIdx === chosenOpt) {
        row.style.background = '#ffebee';
        row.style.border = '1.5px solid #c62828';
        extraBadge = '<span style="color: #c62828; font-weight: 700; margin-left: 8px;">✗ Your Choice</span>';
      }

      row.innerHTML = `
        <div class="cbt-opt-text"><strong>${letters[oIdx]})</strong> ${optText} ${extraBadge}</div>
      `;
      renderMath(row.querySelector('.cbt-opt-text'));
      solOptionsGroup.appendChild(row);
    });
  }

  // Explanation Box Content
  const explText = (isHi && q.explanationHi) ? q.explanationHi : (q.explanation || 'No step-by-step explanation provided.');
  const explImages = (isHi && q.explanationImagesHi && q.explanationImagesHi.length) 
    ? q.explanationImagesHi 
    : (q.explanationImages || (q.explanationImageDriveLink ? [q.explanationImageDriveLink] : []));

  solExplanationText.innerHTML = formatTextWithImages(explText, explImages);
  renderMath(solExplanationText);
}

// Check Answer in Reattempt Mode
btnCheckReattemptAnswer.addEventListener('click', () => {
  const q = state.allQuestions[state.solCurrentQIdx];
  if (state.reattemptSelections[q.id] === undefined) {
    alert('Please select an option first!');
    return;
  }
  state.reattemptChecked[q.id] = true;
  renderSolutionQuestion();
});

// Toggle Reattempt Mode Button
toggleReattemptMode.addEventListener('click', () => {
  state.isReattemptMode = !state.isReattemptMode;
  toggleReattemptMode.classList.toggle('active', state.isReattemptMode);
  toggleReattemptMode.textContent = state.isReattemptMode ? 'Exit Reattempt' : '🔄 Reattempt Mode';
  renderSolutionQuestion();
});

btnBackToResultSummary.addEventListener('click', () => showScreen(resultsScreen));
