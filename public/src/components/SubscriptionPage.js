import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  Button,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
  Alert,
  CircularProgress,
  Paper,
  Slide,
  Tabs,
  Tab,
  Chip,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import CreditCardIcon from '@mui/icons-material/CreditCard';
import AppleIcon from '@mui/icons-material/Apple';
import { getFunctions, httpsCallable } from 'firebase/functions';
import app from '../firebase';

const FALLBACK_PLANS = [
  {
    id: 'monthly',
    name: 'Monthly',
    duration: '1 Month Access',
    price_cents: 49900,
    price_display: 'R499',
    period: 'per month',
    durationDays: 30,
    features: [
      'Full access to all predictions',
      'AI-powered match analysis',
      'Real-time updates',
      'All leagues included',
      'Email support',
    ],
  },
  {
    id: '6months',
    name: '6 Months',
    duration: '6 Months Access',
    price_cents: 249900,
    price_display: 'R2,499',
    period: 'Save vs monthly',
    durationDays: 180,
    featured: true,
    features: [
      'Everything in Monthly',
      '6 months of predictions',
      'Priority support',
      'Advanced analytics',
      'Best value option',
    ],
  },
  {
    id: 'yearly',
    name: 'Annual',
    duration: '1 Year Access',
    price_cents: 419900,
    price_display: 'R4,199',
    period: 'Maximum savings',
    durationDays: 365,
    features: [
      'Everything in 6 Months',
      'Full year of access',
      'Premium support',
      'Early access to features',
      'Maximum savings',
    ],
  },
];

const formatCardNumber = (value) => {
  const digits = value.replace(/\D/g, '').slice(0, 16);
  return digits.replace(/(\d{4})(?=\d)/g, '$1 ').trim();
};

const moneyFromCents = (cents) =>
  `R${(Number(cents || 0) / 100).toLocaleString('en-ZA', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const SubscriptionPage = ({ onBack }) => {
  const [plans, setPlans] = useState(FALLBACK_PLANS);
  const [billingMode, setBillingMode] = useState('sandbox');
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [openModal, setOpenModal] = useState(false);
  const [paymentTab, setPaymentTab] = useState(0);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [cardNumber, setCardNumber] = useState('');
  const [expMonth, setExpMonth] = useState('');
  const [expYear, setExpYear] = useState('');
  const [cvc, setCvc] = useState('');
  const [loading, setLoading] = useState(false);
  const [applePhase, setApplePhase] = useState('idle');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [result, setResult] = useState(null);
  const [emailError, setEmailError] = useState('');
  const scrollLockRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const functions = getFunctions(app, 'us-central1');
        const getPlans = httpsCallable(functions, 'get_billing_plans');
        const res = await getPlans({});
        if (cancelled || res?.data?.error) return;
        if (Array.isArray(res.data.plans) && res.data.plans.length) {
          setPlans(
            res.data.plans.map((p) => ({
              ...p,
              durationDays: p.durationDays || p.duration_days,
            }))
          );
        }
        if (res.data.mode) setBillingMode(res.data.mode);
      } catch (err) {
        console.warn('Using fallback plans (get_billing_plans unavailable)', err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSelectPlan = (plan) => {
    setSelectedPlan(plan);
    setOpenModal(true);
    setError('');
    setSuccess(false);
    setResult(null);
    setEmail('');
    setName('');
    setAddress('');
    setCardNumber('');
    setExpMonth('');
    setExpYear('');
    setCvc('');
    setPaymentTab(0);
    setApplePhase('idle');
  };

  const unlockScroll = useCallback(() => {
    const body = document.body;
    const html = document.documentElement;
    if (body.style.position !== 'fixed') return;
    const scrollY = scrollLockRef.current;
    body.style.position = '';
    body.style.top = '';
    body.style.width = '';
    body.style.overflow = '';
    html.style.overflow = '';
    window.scrollTo(0, scrollY);
  }, []);

  const resetModalState = useCallback(() => {
    setSelectedPlan(null);
    setEmail('');
    setName('');
    setAddress('');
    setCardNumber('');
    setExpMonth('');
    setExpYear('');
    setCvc('');
    setError('');
    setSuccess(false);
    setResult(null);
    setEmailError('');
    setApplePhase('idle');
    setPaymentTab(0);
  }, []);

  const handleCloseModal = () => setOpenModal(false);

  const handleModalExited = () => {
    resetModalState();
    unlockScroll();
  };

  useEffect(() => {
    if (!openModal) return;
    scrollLockRef.current = window.scrollY;
    const body = document.body;
    const html = document.documentElement;
    body.style.position = 'fixed';
    body.style.top = `-${scrollLockRef.current}px`;
    body.style.width = '100%';
    body.style.overflow = 'hidden';
    html.style.overflow = 'hidden';
  }, [openModal]);

  useEffect(() => () => unlockScroll(), [unlockScroll]);

  const runCheckout = async (paymentMethod) => {
    setError('');
    setLoading(true);
    try {
      if (!email || !name) {
        setError('Please fill in all required fields');
        setLoading(false);
        return;
      }

      const functions = getFunctions(app, 'us-central1');
      const checkout = httpsCallable(functions, 'process_sandbox_checkout');

      const payload = {
        email: email.trim().toLowerCase(),
        name: name.trim(),
        plan_id: selectedPlan.id,
        payment_method: paymentMethod,
        address: address.trim() || undefined,
      };

      if (paymentMethod === 'card') {
        payload.card = {
          number: cardNumber.replace(/\s/g, ''),
          exp_month: expMonth,
          exp_year: expYear,
          cvc,
          name: name.trim(),
        };
      }

      const response = await checkout(payload);
      const data = response.data || {};

      if (data.error) {
        setError(data.error);
        setLoading(false);
        setApplePhase('idle');
        return;
      }

      setResult(data);
      setSuccess(true);
      setEmailError(data.email_error || '');
    } catch (err) {
      console.error('Checkout error:', err);
      const msg =
        err?.code === 'functions/not-found'
          ? 'Sandbox checkout function is not deployed yet. Deploy process_sandbox_checkout first.'
          : err.message || 'Payment failed. Please try again.';
      setError(msg);
      setApplePhase('idle');
    } finally {
      setLoading(false);
    }
  };

  const handleCardPay = (e) => {
    e.preventDefault();
    runCheckout('card');
  };

  const handleApplePay = async () => {
    if (!email || !name) {
      setError('Enter your name and email before Apple Pay');
      return;
    }
    setError('');
    setApplePhase('authenticating');
    await new Promise((r) => setTimeout(r, 1400));
    setApplePhase('processing');
    await runCheckout('apple_pay');
    setApplePhase('idle');
  };

  const fieldSx = {
    '& .MuiOutlinedInput-root': {
      background: 'rgba(2,6,23,0.8)',
      color: '#f9fafb',
      borderRadius: '12px',
      '& fieldset': { borderColor: 'rgba(75,85,99,0.5)', borderWidth: '1.5px' },
      '&:hover fieldset': { borderColor: 'rgba(75,85,99,0.7)' },
      '&.Mui-focused fieldset': { borderColor: '#22c55e', borderWidth: '1.5px' },
      '&.Mui-focused': { boxShadow: '0 0 0 3px rgba(34, 197, 94, 0.2)' },
    },
    '& .MuiInputBase-input': { fontSize: { xs: '0.875rem', md: '1rem' }, py: { xs: 1, md: 1.25 } },
    '& .MuiInputBase-input::placeholder': { color: '#6b7280', opacity: 1 },
  };

  const labelSx = {
    display: 'block',
    color: '#d1d5db',
    mb: 0.5,
    fontWeight: 500,
    fontSize: { xs: '0.875rem', md: '1rem' },
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)',
        position: 'relative',
        overflow: 'auto',
        overflowX: 'hidden',
        pt: { xs: 2, md: 10 },
        pb: 4,
        px: { xs: 2, sm: 3 },
      }}
    >
      {onBack && (
        <Box sx={{ position: 'absolute', top: 16, left: { xs: 8, md: 16 }, zIndex: 10 }}>
          <Button
            onClick={onBack}
            sx={{
              color: '#d1d5db',
              fontSize: { xs: '0.875rem', md: '1rem' },
              '&:hover': { color: '#86efac', background: 'rgba(255, 255, 255, 0.1)' },
            }}
          >
            ← Back to Login
          </Button>
        </Box>
      )}

      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          background: `
            radial-gradient(circle at 20% 50%, rgba(34, 197, 94, 0.1) 0%, transparent 50%),
            radial-gradient(circle at 80% 50%, rgba(34, 197, 94, 0.1) 0%, transparent 50%)
          `,
          pointerEvents: 'none',
        }}
      />

      <Container
        maxWidth="lg"
        sx={{
          position: 'relative',
          zIndex: 1,
          mt: { xs: 4, md: 0 },
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          width: '100%',
        }}
      >
        <Box sx={{ textAlign: 'center', mb: { xs: 3, md: 4 }, width: '100%' }}>
          <Chip
            label={
              billingMode === 'sandbox' || billingMode === 'test'
                ? 'SANDBOX CHECKOUT v2 — card / Apple Pay · no real charges'
                : 'LIVE PAYMENTS'
            }
            sx={{
              mb: 2,
              fontWeight: 700,
              letterSpacing: '0.04em',
              background:
                billingMode === 'sandbox' || billingMode === 'test'
                  ? 'rgba(245, 158, 11, 0.2)'
                  : 'rgba(34, 197, 94, 0.2)',
              color:
                billingMode === 'sandbox' || billingMode === 'test' ? '#fbbf24' : '#86efac',
              border: '1px solid rgba(251, 191, 36, 0.4)',
            }}
          />
          <Typography component="div" sx={{ width: { xs: 80, md: 120 }, height: { xs: 80, md: 120 }, mb: 1, display: 'inline-block' }}>
            <img src="/rugby_emoji.png" alt="Rugby Ball" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
          </Typography>
          <Typography
            variant="h1"
            sx={{
              fontSize: { xs: '2rem', md: '3rem' },
              fontWeight: 800,
              mb: 1,
              background: 'linear-gradient(135deg, #f9fafb 0%, #86efac 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            Choose Your Plan
          </Typography>
          <Typography sx={{ fontSize: { xs: '1rem', md: '1.25rem' }, color: '#d1d5db', fontWeight: 300 }}>
            Card or Apple Pay · licence key by email
          </Typography>
        </Box>

        <Grid container spacing={{ xs: 2, md: 3 }} sx={{ mb: 3, justifyContent: 'center', width: '100%' }}>
          {plans.map((plan) => (
            <Grid item xs={12} sm={6} md={4} key={plan.id} sx={{ display: 'flex' }}>
              <Card
                sx={{
                  width: '100%',
                  background: 'linear-gradient(145deg, rgba(15,23,42,0.95), rgba(2,6,23,0.98))',
                  border: plan.featured
                    ? '1.5px solid rgba(34, 197, 94, 0.6)'
                    : '1.5px solid rgba(148,163,184,0.3)',
                  borderRadius: '20px',
                  p: { xs: 2, md: 3 },
                  textAlign: 'center',
                  position: 'relative',
                  transition: 'all 0.3s ease',
                  boxShadow: plan.featured ? '0 0 30px rgba(34, 197, 94, 0.3)' : 'none',
                  '&:hover': {
                    transform: 'translateY(-8px)',
                    boxShadow: '0 20px 40px rgba(34, 197, 94, 0.2)',
                    borderColor: 'rgba(34, 197, 94, 0.5)',
                  },
                }}
              >
                {plan.featured && (
                  <Box
                    sx={{
                      position: 'absolute',
                      top: '0.75rem',
                      right: '0.75rem',
                      background: 'linear-gradient(135deg, #16a34a 0%, #22c55e 100%)',
                      color: 'white',
                      px: 1.25,
                      py: 0.5,
                      borderRadius: '20px',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                    }}
                  >
                    Popular
                  </Box>
                )}
                <Typography sx={{ fontSize: { xs: '1.25rem', md: '1.5rem' }, fontWeight: 700, color: '#f9fafb', mb: 0.5 }}>
                  {plan.name}
                </Typography>
                <Typography sx={{ color: '#9ca3af', fontSize: '0.9rem', mb: 1.5 }}>{plan.duration}</Typography>
                <Typography sx={{ fontSize: { xs: '2.4rem', md: '2.8rem' }, fontWeight: 800, color: '#22c55e', lineHeight: 1, mb: 0.5 }}>
                  {plan.price_display || moneyFromCents(plan.price_cents)}
                </Typography>
                <Typography sx={{ color: '#9ca3af', fontSize: '0.9rem', mb: 2 }}>{plan.period}</Typography>
                <Box component="ul" sx={{ listStyle: 'none', p: 0, m: 0, mb: 2.5, textAlign: 'left' }}>
                  {(plan.features || []).map((feature, idx) => (
                    <Box
                      component="li"
                      key={idx}
                      sx={{
                        color: '#d1d5db',
                        py: 0.7,
                        borderBottom:
                          idx < plan.features.length - 1 ? '1px solid rgba(255, 255, 255, 0.1)' : 'none',
                        display: 'flex',
                        gap: 0.75,
                        fontSize: '0.9rem',
                        '&::before': { content: '"✓"', color: '#22c55e', fontWeight: 700 },
                      }}
                    >
                      {feature}
                    </Box>
                  ))}
                </Box>
                <Button
                  variant="contained"
                  fullWidth
                  onClick={() => handleSelectPlan(plan)}
                  sx={{
                    background: 'linear-gradient(135deg, #16a34a 0%, #22c55e 100%)',
                    color: 'white',
                    py: 1.25,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    borderRadius: '12px',
                    '&:hover': {
                      background: 'linear-gradient(135deg, #22c55e 0%, #4ade80 100%)',
                      transform: 'translateY(-2px)',
                    },
                  }}
                >
                  Select Plan
                </Button>
              </Card>
            </Grid>
          ))}
        </Grid>

        <Alert
          severity="info"
          sx={{
            maxWidth: 720,
            width: '100%',
            background: 'rgba(30, 41, 59, 0.9)',
            color: '#cbd5e1',
            border: '1px solid rgba(148,163,184,0.3)',
            '& .MuiAlert-icon': { color: '#38bdf8' },
          }}
        >
          Test cards: <strong>4242 4242 4242 4242</strong> (success) ·{' '}
          <strong>4000 0000 0000 0002</strong> (decline) · Apple Pay is simulated Face ID.
        </Alert>
      </Container>

      <Dialog
        open={openModal}
        onClose={handleCloseModal}
        maxWidth="sm"
        fullWidth
        TransitionComponent={Slide}
        TransitionProps={{
          direction: 'down',
          timeout: { enter: 300, exit: 250 },
          onExited: handleModalExited,
        }}
        PaperProps={{
          sx: {
            background: 'linear-gradient(145deg, rgba(15,23,42,0.98), rgba(2,6,23,1))',
            border: '1.5px solid rgba(148,163,184,0.5)',
            borderRadius: '20px',
            boxShadow: '0 30px 60px rgba(0,0,0,0.95)',
            maxHeight: '90vh',
            m: { xs: 2, md: 2 },
            width: { xs: 'calc(100% - 32px)', md: 'auto' },
            maxWidth: { xs: 'calc(100% - 32px)', md: '640px' },
          },
        }}
        sx={{
          backdropFilter: 'blur(10px)',
          '& .MuiBackdrop-root': { backgroundColor: 'rgba(0, 0, 0, 0.7)' },
        }}
      >
        <DialogTitle sx={{ color: '#f9fafb', position: 'relative', p: { xs: 2, md: 3 }, pr: 8 }}>
          <Typography sx={{ fontSize: { xs: '1.4rem', md: '1.8rem' }, fontWeight: 700, mb: 0.5 }}>
            {success ? 'You\'re in' : 'Secure checkout'}
          </Typography>
          <Typography sx={{ color: '#9ca3af', fontSize: '0.9rem' }}>
            {success
              ? 'Save this licence key to sign in'
              : 'Sandbox payment · invoice emailed · licence delivery'}
          </Typography>
          <IconButton
            onClick={handleCloseModal}
            aria-label="Close"
            sx={{
              position: 'absolute',
              top: 12,
              right: 12,
              color: '#f9fafb',
              background: 'rgba(255,255,255,0.08)',
            }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>

        <DialogContent sx={{ p: { xs: 2, md: 3 }, pt: 1, overflowY: 'auto' }}>
          {success && result ? (
            <Box sx={{ textAlign: 'center', py: { xs: 2, md: 3 } }}>
              <Typography
                sx={{
                  color: '#9ca3af',
                  fontSize: 12,
                  letterSpacing: 2,
                  textTransform: 'uppercase',
                  mb: 1.5,
                }}
              >
                Licence key
              </Typography>
              <Typography
                sx={{
                  color: '#86efac',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  fontSize: { xs: '1.35rem', md: '1.75rem' },
                  fontWeight: 700,
                  letterSpacing: { xs: 2, md: 3 },
                  lineHeight: 1.4,
                  wordBreak: 'break-all',
                }}
              >
                {result.license_key}
              </Typography>
              <Typography sx={{ color: '#94a3b8', fontSize: 13, mt: 2 }}>
                {result.email_sent
                  ? 'Also sent to your email.'
                  : 'Copy this key — email was not sent.'}
              </Typography>
              {emailError && (
                <Alert severity="warning" sx={{ mt: 2, textAlign: 'left' }}>
                  {emailError}
                </Alert>
              )}
            </Box>
          ) : (
            <Box>
              {selectedPlan && (
                <Paper
                  sx={{
                    mb: 2,
                    p: 1.75,
                    background: 'rgba(2,6,23,0.6)',
                    border: '1px solid rgba(75,85,99,0.3)',
                    borderRadius: '12px',
                  }}
                >
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', color: '#d1d5db', mb: 0.5 }}>
                    <span>{selectedPlan.name} plan</span>
                    <span>{selectedPlan.durationDays || selectedPlan.duration_days} days</span>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, color: '#22c55e', fontSize: '1.15rem' }}>
                    <span>Total (incl. VAT)</span>
                    <span>{selectedPlan.price_display || moneyFromCents(selectedPlan.price_cents)}</span>
                  </Box>
                </Paper>
              )}

              <Box sx={{ mb: 2 }}>
                <Typography component="label" sx={labelSx}>Email *</Typography>
                <TextField fullWidth type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="you@example.com" sx={fieldSx} />
              </Box>
              <Box sx={{ mb: 2 }}>
                <Typography component="label" sx={labelSx}>Full name *</Typography>
                <TextField fullWidth value={name} onChange={(e) => setName(e.target.value)} required placeholder="Jane Citizen" sx={fieldSx} />
              </Box>
              <Box sx={{ mb: 2 }}>
                <Typography component="label" sx={labelSx}>Billing address (optional)</Typography>
                <TextField fullWidth value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Street, City, South Africa" sx={fieldSx} />
              </Box>

              <Tabs
                value={paymentTab}
                onChange={(_, v) => setPaymentTab(v)}
                sx={{
                  mb: 2,
                  minHeight: 42,
                  '& .MuiTab-root': { color: '#94a3b8', textTransform: 'none', fontWeight: 600, minHeight: 42 },
                  '& .Mui-selected': { color: '#86efac' },
                  '& .MuiTabs-indicator': { backgroundColor: '#22c55e' },
                }}
              >
                <Tab icon={<CreditCardIcon />} iconPosition="start" label="Card" />
                <Tab icon={<AppleIcon />} iconPosition="start" label="Apple Pay" />
              </Tabs>

              {paymentTab === 0 ? (
                <Box component="form" onSubmit={handleCardPay}>
                  <Box sx={{ mb: 2 }}>
                    <Typography component="label" sx={labelSx}>Card number *</Typography>
                    <TextField
                      fullWidth
                      value={cardNumber}
                      onChange={(e) => setCardNumber(formatCardNumber(e.target.value))}
                      placeholder="4242 4242 4242 4242"
                      inputProps={{ inputMode: 'numeric', autoComplete: 'cc-number' }}
                      sx={fieldSx}
                    />
                  </Box>
                  <Grid container spacing={1.5} sx={{ mb: 2 }}>
                    <Grid item xs={4}>
                      <Typography component="label" sx={labelSx}>MM</Typography>
                      <TextField fullWidth value={expMonth} onChange={(e) => setExpMonth(e.target.value.replace(/\D/g, '').slice(0, 2))} placeholder="12" sx={fieldSx} />
                    </Grid>
                    <Grid item xs={4}>
                      <Typography component="label" sx={labelSx}>YY</Typography>
                      <TextField fullWidth value={expYear} onChange={(e) => setExpYear(e.target.value.replace(/\D/g, '').slice(0, 2))} placeholder="30" sx={fieldSx} />
                    </Grid>
                    <Grid item xs={4}>
                      <Typography component="label" sx={labelSx}>CVC</Typography>
                      <TextField fullWidth value={cvc} onChange={(e) => setCvc(e.target.value.replace(/\D/g, '').slice(0, 4))} placeholder="123" sx={fieldSx} />
                    </Grid>
                  </Grid>

                  {error && (
                    <Alert severity="error" sx={{ mb: 2, background: 'rgba(239,68,68,0.12)', color: '#fca5a5' }}>
                      {error}
                    </Alert>
                  )}

                  <Button
                    type="submit"
                    fullWidth
                    disabled={loading}
                    variant="contained"
                    sx={{
                      py: 1.4,
                      fontWeight: 700,
                      borderRadius: '12px',
                      background: loading ? 'rgba(55,65,81,1)' : 'linear-gradient(135deg, #16a34a 0%, #22c55e 100%)',
                    }}
                  >
                    {loading ? (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <CircularProgress size={18} sx={{ color: 'white' }} />
                        Processing…
                      </Box>
                    ) : (
                      `Pay ${selectedPlan?.price_display || ''} (test)`
                    )}
                  </Button>
                </Box>
              ) : (
                <Box>
                  <Paper
                    sx={{
                      p: 2.5,
                      mb: 2,
                      borderRadius: '16px',
                      background: '#000',
                      border: '1px solid rgba(255,255,255,0.12)',
                      textAlign: 'center',
                    }}
                  >
                    <AppleIcon sx={{ fontSize: 36, color: '#fff', mb: 1 }} />
                    <Typography sx={{ color: '#fff', fontWeight: 600, mb: 0.5 }}>
                      Apple Pay (sandbox)
                    </Typography>
                    <Typography sx={{ color: '#94a3b8', fontSize: 13, mb: 2 }}>
                      Simulates Face ID confirmation, then runs the same invoice + license pipeline.
                    </Typography>
                    {applePhase === 'authenticating' && (
                      <Typography sx={{ color: '#86efac', mb: 1 }}>Confirming with Face ID…</Typography>
                    )}
                    {error && (
                      <Alert severity="error" sx={{ mb: 2, background: 'rgba(239,68,68,0.12)', color: '#fca5a5' }}>
                        {error}
                      </Alert>
                    )}
                    <Button
                      fullWidth
                      disabled={loading || applePhase !== 'idle'}
                      onClick={handleApplePay}
                      sx={{
                        py: 1.4,
                        borderRadius: '12px',
                        background: '#fff',
                        color: '#000',
                        fontWeight: 700,
                        textTransform: 'none',
                        fontSize: '1.05rem',
                        '&:hover': { background: '#e5e5e5' },
                      }}
                    >
                      {loading || applePhase !== 'idle' ? (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <CircularProgress size={18} />
                          {applePhase === 'authenticating' ? 'Face ID…' : 'Processing…'}
                        </Box>
                      ) : (
                        <>
                          <AppleIcon sx={{ mr: 1 }} /> Pay with Apple Pay
                        </>
                      )}
                    </Button>
                  </Paper>
                </Box>
              )}
            </Box>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
};

export default SubscriptionPage;
