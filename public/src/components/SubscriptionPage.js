import React, { useState, useEffect } from 'react';
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
  DialogActions,
  IconButton,
  Alert,
  CircularProgress,
  Paper,
  useMediaQuery,
  useTheme,
  Fade,
  Slide,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { getFunctions, httpsCallable } from 'firebase/functions';
import app from '../firebase';

const SubscriptionPage = ({ onBack }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [openModal, setOpenModal] = useState(false);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [licenseKey, setLicenseKey] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [emailError, setEmailError] = useState('');
  const [emailSent, setEmailSent] = useState(true);

  const plans = [
    {
      id: 'monthly',
      name: 'Monthly',
      duration: '1 Month Access',
      price: 29,
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
      price: 149,
      period: 'Save $25',
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
      price: 249,
      period: 'Save $99',
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

  const handleSelectPlan = (plan) => {
    setSelectedPlan(plan);
    setOpenModal(true);
    setError('');
    setSuccess(false);
    setEmail('');
    setName('');
  };

  const handleCloseModal = () => {
    setOpenModal(false);
    setSelectedPlan(null);
    setEmail('');
    setName('');
    setError('');
    setSuccess(false);
    setLicenseKey('');
    setExpiresAt('');
    setEmailError('');
    setEmailSent(true);
  };

  // Prevent background scrolling when modal is open
  useEffect(() => {
    if (openModal) {
      // Store original scroll position
      const scrollY = window.scrollY;
      const body = document.body;
      const html = document.documentElement;
      
      // Lock scroll
      body.style.position = 'fixed';
      body.style.top = `-${scrollY}px`;
      body.style.width = '100%';
      body.style.overflow = 'hidden';
      html.style.overflow = 'hidden';
      
      return () => {
        // Restore scroll when modal closes
        body.style.position = '';
        body.style.top = '';
        body.style.width = '';
        body.style.overflow = '';
        html.style.overflow = '';
        window.scrollTo(0, scrollY);
      };
    }
  }, [openModal]);

  const handlePayment = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (!email || !name) {
        setError('Please fill in all required fields');
        setLoading(false);
        return;
      }

      const functions = getFunctions(app, 'us-central1');
      const generateLicenseKey = httpsCallable(functions, 'generate_license_key_with_email');

      const requestData = {
        email: email.trim().toLowerCase(),
        name: name.trim(),
        subscription_type: selectedPlan.id,
        duration_days: selectedPlan.durationDays,
        amount: selectedPlan.price,
      };

      console.log('📤 Sending request to Firebase Function:', requestData);
      const result = await generateLicenseKey(requestData);

      if (result.data.error) {
        setError(result.data.error);
        setLoading(false);
        return;
      }

      // Log email status
      if (result.data.email_sent !== undefined) {
        setEmailSent(result.data.email_sent);
        if (result.data.email_sent) {
          console.log('✅ Email sent successfully!');
          console.log('📧 Sent to:', email);
        } else {
          console.warn('⚠️ Email was NOT sent!');
          if (result.data.email_error) {
            console.error('❌ Email error:', result.data.email_error);
            setEmailError(result.data.email_error);
          }
          console.warn('⚠️ Check Firebase Functions logs for details');
          console.warn('⚠️ License key was still generated:', result.data.license_key ? 'Yes' : 'No');
        }
      } else {
        console.warn('⚠️ email_sent status not in response');
        setEmailSent(true); // Default to true if not specified
      }

      if (result.data.license_key) {
        setLicenseKey(result.data.license_key);
        setExpiresAt(result.data.expires_at);
        setSuccess(true);

        // Log license key info (for debugging - not shown to user)
        console.log('🔑 License Key Generated:', result.data.license_key);
        console.log('📅 Expires At:', result.data.expires_at ? new Date(result.data.expires_at * 1000).toLocaleString() : 'N/A');
      } else {
        setError('Failed to generate license key. Please try again.');
      }
    } catch (err) {
      console.error('❌ Payment error:', err);
      setError(err.message || 'Payment failed. Please try again.');
    } finally {
      setLoading(false);
    }
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
      {/* Back Button */}
      {onBack && (
        <Box sx={{ position: 'absolute', top: 16, left: { xs: 8, md: 16 }, zIndex: 10 }}>
          <Button
            onClick={onBack}
            sx={{
              color: '#d1d5db',
              fontSize: { xs: '0.875rem', md: '1rem' },
              '&:hover': {
                color: '#86efac',
                background: 'rgba(255, 255, 255, 0.1)',
              },
            }}
          >
            ← Back to Login
          </Button>
        </Box>
      )}

      {/* Background gradient overlay */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: `
            radial-gradient(circle at 20% 50%, rgba(34, 197, 94, 0.1) 0%, transparent 50%),
            radial-gradient(circle at 80% 50%, rgba(34, 197, 94, 0.1) 0%, transparent 50%)
          `,
          pointerEvents: 'none',
        }}
      />

      <Container 
        maxWidth="lg" 
        disableGutters={false}
        sx={{ 
          position: 'relative', 
          zIndex: 1, 
          mt: { xs: 4, md: 0 },
          px: { xs: 2, sm: 3 },
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          width: '100%',
          '&.MuiContainer-root': {
            paddingLeft: { xs: '16px', sm: '24px' },
            paddingRight: { xs: '16px', sm: '24px' },
          },
        }}
      >
        {/* Header */}
        <Box sx={{ textAlign: 'center', mb: { xs: 3, md: 6 }, width: '100%' }}>
          <Typography
            sx={{
              width: { xs: '80px', md: '120px' },
              height: { xs: '80px', md: '120px' },
              mb: 1,
              filter: 'drop-shadow(0 4px 8px rgba(0, 0, 0, 0.3))',
              display: 'inline-block',
            }}
            component="div"
          >
            <img src="/rugby_emoji.png" alt="Rugby Ball" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
          </Typography>
          <Typography
            variant="h1"
            sx={{
              fontSize: { xs: '2rem', md: '3rem' },
              fontWeight: 800,
              mb: 1,
              color: '#f9fafb',
              background: 'linear-gradient(135deg, #f9fafb 0%, #86efac 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Choose Your Plan
          </Typography>
          <Typography
            sx={{
              fontSize: { xs: '1rem', md: '1.25rem' },
              color: '#d1d5db',
              fontWeight: 300,
            }}
          >
            Unlock premium AI-powered rugby predictions
          </Typography>
        </Box>

        {/* Plans Grid */}
        <Box sx={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
          <Grid 
            container 
            spacing={{ xs: 2, md: 3 }} 
            sx={{ 
              mb: { xs: 2, md: 3 },
              justifyContent: 'center',
              alignItems: 'stretch',
              width: '100%',
              maxWidth: '100%',
              margin: 0,
            }}
          >
            {plans.map((plan) => (
              <Grid 
                item 
                xs={12} 
                sm={6} 
                md={4} 
                key={plan.id} 
                sx={{ 
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'stretch',
                  width: '100%',
                  minWidth: 0,
                }}
              >
                <Card
                  sx={{
                    width: '100%',
                    maxWidth: { xs: '100%', sm: 'none', md: '100%' },
                    background: 'linear-gradient(145deg, rgba(15,23,42,0.95), rgba(2,6,23,0.98))',
                  border: plan.featured
                    ? '1.5px solid rgba(34, 197, 94, 0.6)'
                    : '1.5px solid rgba(148,163,184,0.3)',
                  borderRadius: '20px',
                  p: { xs: 2, md: 3.125 },
                  textAlign: 'center',
                  position: 'relative',
                  overflow: 'hidden',
                  transition: 'all 0.3s ease',
                  boxShadow: plan.featured ? '0 0 30px rgba(34, 197, 94, 0.3)' : 'none',
                  '&::before': {
                    content: '""',
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: '4px',
                    background: 'linear-gradient(90deg, #16a34a 0%, #22c55e 100%)',
                    transform: plan.featured ? 'scaleX(1)' : 'scaleX(0)',
                    transition: 'transform 0.3s ease',
                  },
                  '&:hover': {
                    transform: 'translateY(-8px)',
                    boxShadow: '0 20px 40px rgba(34, 197, 94, 0.2)',
                    borderColor: 'rgba(34, 197, 94, 0.5)',
                    '&::before': {
                      transform: 'scaleX(1)',
                    },
                  },
                }}
              >
                {plan.featured && (
                  <Box
                    sx={{
                      position: 'absolute',
                      top: { xs: '0.75rem', md: '1rem' },
                      right: { xs: '0.75rem', md: '1rem' },
                      background: 'linear-gradient(135deg, #16a34a 0%, #22c55e 100%)',
                      color: 'white',
                      px: { xs: 1, md: 1.25 },
                      py: { xs: 0.5, md: 0.625 },
                      borderRadius: '20px',
                      fontSize: { xs: '0.65rem', md: '0.75rem' },
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                    }}
                  >
                    Popular
                  </Box>
                )}

                <Typography
                  sx={{
                    fontSize: { xs: '1.25rem', md: '1.5rem' },
                    fontWeight: 700,
                    color: '#f9fafb',
                    mb: 0.5,
                  }}
                >
                  {plan.name}
                </Typography>
                <Typography
                  sx={{
                    color: '#9ca3af',
                    fontSize: { xs: '0.85rem', md: '0.9rem' },
                    mb: { xs: 1.5, md: 1.875 },
                  }}
                >
                  {plan.duration}
                </Typography>
                <Typography
                  sx={{
                    fontSize: { xs: '2.5rem', md: '3rem' },
                    fontWeight: 800,
                    color: '#22c55e',
                    mb: 0.5,
                    lineHeight: 1,
                  }}
                >
                  ${plan.price}
                </Typography>
                <Typography
                  sx={{
                    color: '#9ca3af',
                    fontSize: { xs: '0.85rem', md: '0.9rem' },
                    mb: { xs: 2, md: 2.5 },
                  }}
                >
                  {plan.period}
                </Typography>

                <Box
                  component="ul"
                  sx={{
                    listStyle: 'none',
                    p: 0,
                    m: 0,
                    mb: { xs: 2, md: 2.5 },
                    textAlign: 'left',
                  }}
                >
                  {plan.features.map((feature, idx) => (
                    <Box
                      component="li"
                      key={idx}
                      sx={{
                        color: '#d1d5db',
                        py: { xs: 0.625, md: 0.75 },
                        borderBottom: idx < plan.features.length - 1 ? '1px solid rgba(255, 255, 255, 0.1)' : 'none',
                        display: 'flex',
                        alignItems: 'center',
                        gap: { xs: 0.625, md: 0.75 },
                        fontSize: { xs: '0.875rem', md: '1rem' },
                        '&::before': {
                          content: '"✓"',
                          color: '#22c55e',
                          fontWeight: 700,
                          fontSize: { xs: '1rem', md: '1.2rem' },
                          flexShrink: 0,
                        },
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
                    py: { xs: 1, md: 1.25 },
                    px: { xs: 1.5, md: 2 },
                    fontSize: { xs: '1rem', md: '1.1rem' },
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    borderRadius: '12px',
                    border: 'none',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      transform: 'translateY(-2px)',
                      boxShadow: '0 8px 20px rgba(34, 197, 94, 0.4)',
                      background: 'linear-gradient(135deg, #22c55e 0%, #4ade80 100%)',
                    },
                    '&:active': {
                      transform: 'translateY(0)',
                    },
                  }}
                >
                  Select Plan
                </Button>
              </Card>
            </Grid>
          ))}
        </Grid>
        </Box>
      </Container>

      {/* Payment Modal */}
      <Dialog
        open={openModal}
        onClose={handleCloseModal}
        maxWidth="sm"
        fullWidth
        TransitionComponent={Slide}
        TransitionProps={{
          direction: 'down',
          timeout: { enter: 300, exit: 250 },
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
            maxWidth: { xs: 'calc(100% - 32px)', md: '600px' },
            transition: 'all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
            '&.MuiDialog-paper': {
              '&.MuiDialog-paperEntering': {
                animation: 'modalEnter 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
              },
              '&.MuiDialog-paperExiting': {
                animation: 'modalExit 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
              },
            },
            '@keyframes modalEnter': {
              '0%': {
                opacity: 0,
                transform: 'scale(0.9) translateY(-30px)',
              },
              '100%': {
                opacity: 1,
                transform: 'scale(1) translateY(0)',
              },
            },
            '@keyframes modalExit': {
              '0%': {
                opacity: 1,
                transform: 'scale(1) translateY(0)',
              },
              '100%': {
                opacity: 0,
                transform: 'scale(0.95) translateY(-20px)',
              },
            },
          },
        }}
        sx={{
          backdropFilter: 'blur(10px)',
          '& .MuiBackdrop-root': {
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            transition: 'opacity 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          },
        }}
      >
        <DialogTitle
          sx={{
            color: '#f9fafb',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            p: { xs: 2, md: 3 },
            pb: { xs: 1, md: 2 },
            pr: { xs: 2, md: 10 }, // Add right padding to prevent overlap
            position: 'relative',
          }}
        >
          <Box sx={{ flex: 1, pr: { xs: 0, md: 2 } }}>
            <Typography
              sx={{
                fontSize: { xs: '1.5rem', md: '2rem' },
                fontWeight: 700,
                color: '#f9fafb',
                mb: 0.5,
                pr: { xs: 0, md: 1 },
              }}
            >
              Complete Your Purchase
            </Typography>
            <Typography
              sx={{
                color: '#9ca3af',
                fontSize: { xs: '0.875rem', md: '1rem' },
                pr: { xs: 0, md: 1 },
              }}
            >
              Enter your details to receive your license key
            </Typography>
          </Box>
          <IconButton
            onClick={handleCloseModal}
            sx={{
              position: 'absolute',
              top: { xs: 8, md: 16 },
              right: { xs: 8, md: 16 },
              background: 'rgba(255, 255, 255, 0.1)',
              color: '#f9fafb',
              width: { xs: 36, md: 40 },
              height: { xs: 36, md: 40 },
              borderRadius: '12px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
              transform: 'scale(1)',
              flexShrink: 0,
              zIndex: 1,
              WebkitTapHighlightColor: 'transparent',
              touchAction: 'manipulation',
              '&:hover': {
                background: 'rgba(239, 68, 68, 0.2)',
                borderColor: 'rgba(239, 68, 68, 0.4)',
                transform: 'rotate(90deg) scale(1.1)',
                boxShadow: '0 4px 12px rgba(239, 68, 68, 0.3)',
                color: '#fca5a5',
              },
              '&:active': {
                background: 'rgba(239, 68, 68, 0.3)',
                borderColor: 'rgba(239, 68, 68, 0.5)',
                transform: 'rotate(90deg) scale(0.9)',
                boxShadow: '0 2px 8px rgba(239, 68, 68, 0.4)',
                color: '#fca5a5',
              },
              '&:focus': {
                background: 'rgba(239, 68, 68, 0.2)',
                borderColor: 'rgba(239, 68, 68, 0.4)',
                transform: 'rotate(90deg) scale(1.05)',
              },
              '& svg': {
                transition: 'transform 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
              },
              '&:hover svg, &:active svg, &:focus svg': {
                transform: 'scale(1.1)',
              },
              // Mobile-specific: ensure animation works on touch
              '@media (hover: none) and (pointer: coarse)': {
                '&:active': {
                  background: 'rgba(239, 68, 68, 0.3)',
                  borderColor: 'rgba(239, 68, 68, 0.5)',
                  transform: 'rotate(90deg) scale(0.9)',
                  boxShadow: '0 2px 8px rgba(239, 68, 68, 0.4)',
                  color: '#fca5a5',
                  '& svg': {
                    transform: 'scale(1.1)',
                  },
                },
              },
            }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>

        <DialogContent sx={{ 
          p: { xs: 2, md: 3 }, 
          pt: { xs: 2, md: 2 },
          overflowY: 'auto',
          maxHeight: { xs: 'calc(90vh - 180px)', md: 'calc(90vh - 180px)' },
        }}>
          {success ? (
            <Box
              sx={{
                background: 'rgba(34, 197, 94, 0.1)',
                border: '1px solid rgba(34, 197, 94, 0.3)',
                borderRadius: '12px',
                padding: '1.5rem',
                marginTop: '2rem',
                textAlign: 'center',
              }}
            >
              <Typography
                sx={{
                  color: '#22c55e',
                  marginBottom: '1rem',
                  fontSize: '1.5rem',
                  fontWeight: 700,
                }}
              >
                ✅ Payment Successful!
              </Typography>
              <Typography
                sx={{
                  color: '#d1d5db',
                  marginBottom: '0.5rem',
                }}
              >
                Your subscription has been activated!
              </Typography>
              <Typography
                sx={{
                  marginTop: '1rem',
                  fontSize: '1rem',
                  color: '#d1d5db',
                }}
              >
                <strong>Your license key has been sent to your email address.</strong>
              </Typography>
              <Typography
                sx={{
                  marginTop: '1rem',
                  fontSize: '0.9rem',
                  color: '#9ca3af',
                }}
              >
                Please check your inbox (and spam folder) for an email containing your license key and activation instructions.
              </Typography>
              <Typography
                sx={{
                  marginTop: '1rem',
                  fontSize: '0.9rem',
                  color: '#9ca3af',
                }}
              >
                You can use the license key from the email to login to your account.
              </Typography>
              {emailError && (
                <Typography
                  sx={{
                    marginTop: '1rem',
                    fontSize: '0.9rem',
                    color: '#fbbf24',
                  }}
                >
                  ⚠️ <strong>Email sending failed:</strong> {emailError}<br />
                  Your license key was generated successfully. Please contact support if you need assistance.
                </Typography>
              )}
              {!emailSent && !emailError && (
                <Typography
                  sx={{
                    marginTop: '1rem',
                    fontSize: '0.9rem',
                    color: '#fbbf24',
                  }}
                >
                  ⚠️ Email sending failed. Please check your email or contact support with your license key.
                </Typography>
              )}
            </Box>
          ) : (
            <Box component="form" onSubmit={handlePayment}>
              <Box sx={{ mb: { xs: 2, md: 2.5 } }}>
                <Typography
                  component="label"
                  sx={{
                    display: 'block',
                    color: '#d1d5db',
                    mb: 0.5,
                    fontWeight: 500,
                    fontSize: { xs: '0.875rem', md: '1rem' },
                  }}
                >
                  Email Address *
                </Typography>
                <TextField
                  fullWidth
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  placeholder="your.email@example.com"
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      background: 'rgba(2,6,23,0.8)',
                      color: '#f9fafb',
                      borderRadius: '12px',
                      '& fieldset': {
                        borderColor: 'rgba(75,85,99,0.5)',
                        borderWidth: '1.5px',
                      },
                      '&:hover fieldset': {
                        borderColor: 'rgba(75,85,99,0.7)',
                      },
                      '&.Mui-focused fieldset': {
                        borderColor: '#22c55e',
                        borderWidth: '1.5px',
                      },
                      '&.Mui-focused': {
                        boxShadow: '0 0 0 3px rgba(34, 197, 94, 0.2)',
                      },
                    },
                    '& .MuiInputBase-input': {
                      fontSize: { xs: '0.875rem', md: '1rem' },
                      py: { xs: 1, md: 1.25 },
                    },
                    '& .MuiInputBase-input::placeholder': {
                      color: '#6b7280',
                      opacity: 1,
                    },
                  }}
                />
              </Box>

              <Box sx={{ mb: { xs: 2, md: 2.5 } }}>
                <Typography
                  component="label"
                  sx={{
                    display: 'block',
                    color: '#d1d5db',
                    mb: 0.5,
                    fontWeight: 500,
                    fontSize: { xs: '0.875rem', md: '1rem' },
                  }}
                >
                  Full Name *
                </Typography>
                <TextField
                  fullWidth
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  placeholder="John Doe"
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      background: 'rgba(2,6,23,0.8)',
                      color: '#f9fafb',
                      borderRadius: '12px',
                      '& fieldset': {
                        borderColor: 'rgba(75,85,99,0.5)',
                        borderWidth: '1.5px',
                      },
                      '&:hover fieldset': {
                        borderColor: 'rgba(75,85,99,0.7)',
                      },
                      '&.Mui-focused fieldset': {
                        borderColor: '#22c55e',
                        borderWidth: '1.5px',
                      },
                      '&.Mui-focused': {
                        boxShadow: '0 0 0 3px rgba(34, 197, 94, 0.2)',
                      },
                    },
                    '& .MuiInputBase-input': {
                      fontSize: { xs: '0.875rem', md: '1rem' },
                      py: { xs: 1, md: 1.25 },
                    },
                    '& .MuiInputBase-input::placeholder': {
                      color: '#6b7280',
                      opacity: 1,
                    },
                  }}
                />
              </Box>

              {selectedPlan && (
                <Paper
                  sx={{
                    mb: 2,
                    p: { xs: 1.5, md: 2 },
                    background: 'rgba(2,6,23,0.6)',
                    border: '1px solid rgba(75,85,99,0.3)',
                    borderRadius: '12px',
                  }}
                >
                  <Box
                    sx={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      color: '#d1d5db',
                      mb: 0.75,
                      fontSize: { xs: '0.875rem', md: '1rem' },
                    }}
                  >
                    <span>Plan:</span>
                    <span>
                      {selectedPlan.id === 'monthly' ? 'Monthly Plan' : 
                       selectedPlan.id === '6months' ? '6 Months Plan' : 'Annual Plan'}
                    </span>
                  </Box>
                  <Box
                    sx={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      color: '#d1d5db',
                      mb: 0.75,
                      fontSize: { xs: '0.875rem', md: '1rem' },
                    }}
                  >
                    <span>Duration:</span>
                    <span>
                      {selectedPlan.durationDays === 30 ? '1 Month' : 
                       selectedPlan.durationDays === 180 ? '6 Months' : '12 Months'}
                    </span>
                  </Box>
                  <Box
                    sx={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      borderTop: '1px solid rgba(255, 255, 255, 0.1)',
                      pt: 1,
                      mt: 1,
                      fontSize: { xs: '1.1rem', md: '1.2rem' },
                      fontWeight: 700,
                      color: '#22c55e',
                    }}
                  >
                    <span>Total:</span>
                    <span>${selectedPlan.price}</span>
                  </Box>
                </Paper>
              )}

              {error && (
                <Alert 
                  severity="error" 
                  sx={{ 
                    mb: 2,
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    color: '#fca5a5',
                  }}
                >
                  {error}
                </Alert>
              )}

              <Button
                type="submit"
                fullWidth
                variant="contained"
                disabled={loading}
                sx={{
                  background: loading
                    ? 'rgba(55, 65, 81, 1)'
                    : 'linear-gradient(135deg, #16a34a 0%, #22c55e 100%)',
                  color: 'white',
                  py: { xs: 1.25, md: 1.5 },
                  fontSize: { xs: '1rem', md: '1.1rem' },
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  borderRadius: '12px',
                  mt: { xs: 1, md: 1.25 },
                  transition: 'all 0.3s ease',
                  '&:hover:not(:disabled)': {
                    transform: 'translateY(-2px)',
                    boxShadow: '0 8px 20px rgba(34, 197, 94, 0.4)',
                    background: 'linear-gradient(135deg, #22c55e 0%, #4ade80 100%)',
                  },
                  '&:disabled': {
                    opacity: 0.6,
                    cursor: 'not-allowed',
                  },
                }}
              >
                {loading ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                    <CircularProgress size={20} sx={{ color: 'white' }} />
                    <span>Processing Payment...</span>
                  </Box>
                ) : (
                  'Complete Purchase'
                )}
              </Button>
            </Box>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
};

export default SubscriptionPage;
