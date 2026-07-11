import React, { useState, useEffect } from 'react';
import styled, { createGlobalStyle, keyframes } from 'styled-components';
import { motion, AnimatePresence, type Variants } from 'framer-motion';

// ============================================================
// 🌍 グローバルスタイル
// ============================================================
const GlobalStyle = createGlobalStyle`
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    -webkit-tap-highlight-color: transparent;
  }

  html, body {
    width: 100%;
    height: 100%;
    overflow: hidden;
    font-family: 'Noto Sans JP', 'Segoe UI', sans-serif;
    background: #1a0011;
    color: #fff;
  }

  #root {
    width: 100%;
    height: 100%;
    overflow-y: auto;
    overflow-x: hidden;
  }

  ::-webkit-scrollbar {
    width: 6px;
  }
  ::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.05);
  }
  ::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, #ff2d78, #b300ff);
    border-radius: 3px;
  }

  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap');
`;

// ============================================================
// 💫 アニメーションキーフレーム
// ============================================================
const sparkle = keyframes`
  0%, 100% { opacity: 1; transform: scale(1) rotate(0deg); }
  50% { opacity: 0.5; transform: scale(0.8) rotate(180deg); }
`;

const gradientShift = keyframes`
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
`;

// ============================================================
// 📐 スタイルドコンポーネント
// ============================================================

const AppContainer = styled.div`
  width: 100%;
  min-height: 100vh;
  background: radial-gradient(ellipse at 50% 0%, #2d001a 0%, #1a0011 70%);
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  overflow: hidden;
`;

// ✨ キラキラ背景パーティクル
const SparkleBackground = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
`;

const SparkleDot = styled.div<{ size: number; left: number; top: number; delay: number }>`
  position: absolute;
  width: ${({ size }) => size}px;
  height: ${({ size }) => size}px;
  left: ${({ left }) => left}%;
  top: ${({ top }) => top}%;
  background: ${({ size }) =>
    size > 5 ? 'radial-gradient(circle, #ffd700, #ff2d78)' : '#fff'};
  border-radius: 50%;
  animation: ${sparkle} ${({ delay }) => 2 + delay}s ease-in-out infinite;
  opacity: ${({ size }) => size > 5 ? 0.6 : 0.3};
  box-shadow: ${({ size }) =>
    size > 5 ? '0 0 10px #ffd700, 0 0 20px #ff2d78' : 'none'};
`;

// 🏠 ヘッダー
const Header = styled(motion.header)`
  width: 100%;
  max-width: 600px;
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 10;
  position: relative;
`;

const Logo = styled(motion.div)`
  font-size: 1.6rem;
  font-weight: 900;
  background: linear-gradient(135deg, #ff2d78, #ffd700, #b300ff);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: ${gradientShift} 3s ease infinite;
  letter-spacing: 2px;
  text-shadow: none;
  display: flex;
  align-items: center;
  gap: 8px;
`;

const HeaderRight = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const NotificationBadge = styled(motion.div)`
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  cursor: pointer;
  position: relative;
  transition: all 0.2s;

  &:hover {
    background: rgba(255, 45, 120, 0.3);
    border-color: #ff2d78;
  }
`;

const NotificationDot = styled.div<{ hasNotification: boolean }>`
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${({ hasNotification }) =>
    hasNotification ? '#ff2d78' : 'transparent'};
  box-shadow: ${({ hasNotification }) =>
    hasNotification ? '0 0 8px #ff2d78' : 'none'};
`;

const AvatarCircle = styled(motion.div)`
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: linear-gradient(135deg, #ff2d78, #b300ff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.3rem;
  cursor: pointer;
  border: 2px solid #ffd700;
  box-shadow: 0 0 15px rgba(255, 45, 120, 0.4);
  transition: all 0.2s;

  &:hover {
    transform: scale(1.1);
    box-shadow: 0 0 25px rgba(255, 45, 120, 0.7);
  }
`;

// 📊 メインコンテンツ
const MainContent = styled.main`
  width: 100%;
  max-width: 600px;
  padding: 0 16px 20px;
  z-index: 10;
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

// 🎯 ステータスカードグリッド
const StatusGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 4px;
`;

const StatusCard = styled(motion.div)<{ gradient?: string; glowColor?: string }>`
  background: ${({ gradient }) =>
    gradient || 'linear-gradient(135deg, #2d001a, #3d002a)'};
  border-radius: 20px;
  padding: 18px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: ${({ glowColor }) =>
    glowColor ? `0 0 20px ${glowColor}` : '0 4px 15px rgba(0,0,0,0.3)'};
  display: flex;
  flex-direction: column;
  gap: 6px;
  position: relative;
  overflow: hidden;
  cursor: default;
  transition: all 0.3s;

  &:hover {
    transform: translateY(-2px);
    box-shadow: ${({ glowColor }) =>
      glowColor
        ? `0 0 30px ${glowColor}, 0 8px 25px rgba(0,0,0,0.4)`
        : '0 8px 25px rgba(0,0,0,0.4)'};
  }
`;

const CardLabel = styled.span`
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 700;
`;

const CardValue = styled.span<{ size?: string; color?: string }>`
  font-size: ${({ size }) => size || '2rem'};
  font-weight: 900;
  color: ${({ color }) => color || '#fff'};
  text-shadow: 0 0 15px ${({ color }) => color || 'transparent'};
  line-height: 1.1;
`;

const CardSubtext = styled.span`
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.4);
`;

const CardEmoji = styled.span`
  position: absolute;
  top: 10px;
  right: 12px;
  font-size: 1.8rem;
  opacity: 0.3;
`;

// 📈 アクティビティエリア
const SectionTitle = styled.h2`
  font-size: 1.1rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  margin-bottom: 4px;
`;

const ActivityList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const ActivityItem = styled(motion.div)`
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 14px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  backdrop-filter: blur(4px);
  transition: all 0.2s;

  &:hover {
    background: rgba(255, 45, 120, 0.08);
    border-color: rgba(255, 45, 120, 0.2);
    transform: translateX(4px);
  }
`;

const ActivityIcon = styled.div`
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #ff2d78, #b300ff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  flex-shrink: 0;
`;

const ActivityContent = styled.div`
  flex: 1;
  min-width: 0;
`;

const ActivityTitle = styled.div`
  font-size: 0.9rem;
  font-weight: 700;
`;

const ActivityTime = styled.div`
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.4);
  margin-top: 2px;
`;

// 🚀 クイックアクション
const QuickActionGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 4px;
`;

const QuickActionBtn = styled(motion.button)<{ btnColor?: string }>`
  background: ${({ btnColor }) =>
    btnColor || 'rgba(255, 255, 255, 0.06)'};
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 14px 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #fff;
  font-family: inherit;
  font-size: 0.75rem;
  font-weight: 700;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;

  &:hover {
    background: ${({ btnColor }) =>
      btnColor || 'rgba(255, 45, 120, 0.15)'};
    border-color: ${({ btnColor }) => btnColor || '#ff2d78'};
    transform: translateY(-3px);
    box-shadow: ${({ btnColor }) =>
      btnColor ? `0 4px 15px ${btnColor}` : '0 4px 15px rgba(255,45,120,0.3)'};
  }

  &:active {
    transform: translateY(0px);
  }
`;

const ActionIcon = styled.span`
  font-size: 1.6rem;
`;

const ActionLabel = styled.span`
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.7);
`;

// 🎬 フッター
const Footer = styled.footer`
  width: 100%;
  max-width: 600px;
  padding: 12px 16px;
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10;
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.2);
  gap: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  margin-top: auto;
`;

// ============================================================
// 📋 ダミーデータ（あとでAPI接続に切り替え）
// ============================================================
const mockActivities = [
  { icon: '💖', title: 'コーデ登録完了！', time: '5分前' },
  { icon: '🌟', title: 'AI採点: 92点 キタコレ！', time: '15分前' },
  { icon: '👯', title: 'ゆきのちゃんがフォロー', time: '30分前' },
  { icon: '💎', title: '週間ランキング2位！', time: '1時間前' },
  { icon: '🔥', title: 'レベル5 達成！', time: '2時間前' },
];

const quickActions = [
  { icon: '📸', label: 'コーデ撮影', color: '#ff2d78' },
  { icon: '📊', label: 'AI採点', color: '#b300ff' },
  { icon: '🏆', label: 'ランキング', color: '#ffd700' },
  { icon: '👯', label: '友達', color: '#00d4ff' },
];

// ============================================================
// 🧩 スパークル背景生成関数
// ============================================================
const generateSparkles = (count: number) => {
  const sparkles = [];
  for (let i = 0; i < count; i++) {
    sparkles.push({
      id: i,
      size: Math.random() * 8 + 2,
      left: Math.random() * 100,
      top: Math.random() * 100,
      delay: Math.random() * 3,
    });
  }
  return sparkles;
};

// ============================================================
// 🏆 メインAppコンポーネント
// ============================================================

const App: React.FC = () => {
  const [sparkles, setSparkles] = useState(generateSparkles(30));
  const [notifications, setNotifications] = useState(true);
  const [userName] = useState('ナナ'); void userName;
  const [score] = useState(2840);
  const [level] = useState(5);
  const [streak] = useState(7);
  const [rank] = useState('#2');

  // ウィンドウリサイズでスパークル再生成
  useEffect(() => {
    const handleResize = () => {
      setSparkles(generateSparkles(30));
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // コンテナバリアント
  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.08,
      },
    },
  };

  const itemVariants: Variants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        type: 'spring',
        stiffness: 120,
        damping: 12,
      },
    },
  };

  return (
    <>
      <GlobalStyle />
      <AppContainer>
        {/* ✨ キラキラ背景 */}
        <SparkleBackground>
          {sparkles.map((s) => (
            <SparkleDot
              key={s.id}
              size={s.size}
              left={s.left}
              top={s.top}
              delay={s.delay}
            />
          ))}
        </SparkleBackground>

        {/* 🏠 ヘッダー */}
        <Header
          initial={{ y: -60, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 100, damping: 15 }}
        >
          <Logo
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            💖 GYARU
          </Logo>
          <HeaderRight>
            <NotificationBadge
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              onClick={() => setNotifications(!notifications)}
            >
              🔔
              <NotificationDot hasNotification={notifications} />
            </NotificationBadge>
            <AvatarCircle
              whileHover={{ scale: 1.1, rotate: 10 }}
              whileTap={{ scale: 0.9 }}
            >
              👑
            </AvatarCircle>
          </HeaderRight>
        </Header>

        {/* 📊 メインコンテンツ */}
        <MainContent
          as={motion.div}
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          {/* 🏆 ステータスグリッド */}
          <StatusGrid>
            <StatusCard
              variants={itemVariants}
              gradient="linear-gradient(135deg, #2d001a, #4a002a)"
              glowColor="rgba(255,45,120,0.3)"
            >
              <CardEmoji>💖</CardEmoji>
              <CardLabel>Score</CardLabel>
              <CardValue color="#ff2d78">{score.toLocaleString()}</CardValue>
              <CardSubtext>+120 today</CardSubtext>
            </StatusCard>

            <StatusCard
              variants={itemVariants}
              gradient="linear-gradient(135deg, #1a002d, #2d004a)"
              glowColor="rgba(179,0,255,0.3)"
            >
              <CardEmoji>⭐</CardEmoji>
              <CardLabel>Level</CardLabel>
              <CardValue color="#b300ff">{level}</CardValue>
              <CardSubtext>Next: 3,000 pts</CardSubtext>
            </StatusCard>

            <StatusCard
              variants={itemVariants}
              gradient="linear-gradient(135deg, #2d1a00, #4a2d00)"
              glowColor="rgba(255,215,0,0.3)"
            >
              <CardEmoji>🔥</CardEmoji>
              <CardLabel>Streak</CardLabel>
              <CardValue color="#ffd700">{streak}日</CardValue>
              <CardSubtext>継続中！</CardSubtext>
            </StatusCard>

            <StatusCard
              variants={itemVariants}
              gradient="linear-gradient(135deg, #001a2d, #002d4a)"
              glowColor="rgba(0,212,255,0.3)"
            >
              <CardEmoji>🏆</CardEmoji>
              <CardLabel>Rank</CardLabel>
              <CardValue color="#00d4ff">{rank}</CardValue>
              <CardSubtext>今週の順位</CardSubtext>
            </StatusCard>
          </StatusGrid>

          {/* 🚀 クイックアクション */}
          <motion.div variants={itemVariants}>
            <SectionTitle>🚀 クイックアクション</SectionTitle>
            <QuickActionGrid>
              {quickActions.map((action, idx) => (
                <QuickActionBtn
                  key={idx}
                  btnColor={action.color}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.92 }}
                >
                  <ActionIcon>{action.icon}</ActionIcon>
                  <ActionLabel>{action.label}</ActionLabel>
                </QuickActionBtn>
              ))}
            </QuickActionGrid>
          </motion.div>

          {/* 📋 最近のアクティビティ */}
          <motion.div variants={itemVariants}>
            <SectionTitle>📋 最近のアクティビティ</SectionTitle>
            <ActivityList>
              <AnimatePresence>
                {mockActivities.map((activity, idx) => (
                  <ActivityItem
                    key={idx}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.1, type: 'spring', stiffness: 80 }}
                    whileHover={{ x: 4 }}
                  >
                    <ActivityIcon>{activity.icon}</ActivityIcon>
                    <ActivityContent>
                      <ActivityTitle>{activity.title}</ActivityTitle>
                      <ActivityTime>{activity.time}</ActivityTime>
                    </ActivityContent>
                  </ActivityItem>
                ))}
              </AnimatePresence>
            </ActivityList>
          </motion.div>
        </MainContent>

        {/* 🎬 フッター */}
        <Footer>
          <span>✨ Powered by Antigravity ✨</span>
          <span>|</span>
          <span>v1.0.0</span>
        </Footer>
      </AppContainer>
    </>
  );
};

export default App;
