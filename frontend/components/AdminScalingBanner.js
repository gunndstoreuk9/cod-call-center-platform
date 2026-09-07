'use client'

export default function AdminScalingBanner() {
  return (
    <section className="scaleBanner">
      <div className="ambient ambientOne" />
      <div className="ambient ambientTwo" />
      <div className="gridOverlay" />

      <div className="copy">
        <div className="eyebrow">
          <span className="liveDot" />
          COD OPS PERFORMANCE
        </div>

        <h2>
          Move to the
          <span> Scaling Team</span>
        </h2>

        <p>
          Strong confirmation. Better delivery quality. Faster growth.
        </p>

        <div className="miniStats">
          <div>
            <strong>01</strong>
            <span>Confirm</span>
          </div>
          <i />
          <div>
            <strong>02</strong>
            <span>Deliver</span>
          </div>
          <i />
          <div>
            <strong>03</strong>
            <span>Scale</span>
          </div>
        </div>
      </div>

      <div className="motionZone">
        <div className="trackGlow" />

        <div className="checkpoint checkpointOne">
          <span>CONFIRM</span>
        </div>

        <div className="checkpoint checkpointTwo">
          <span>DELIVER</span>
        </div>

        <div className="checkpoint checkpointThree">
          <span>SCALE</span>
        </div>

        <div className="runnerTravel">
          <div className="speedLines">
            <span />
            <span />
            <span />
          </div>

          <div className="runnerLabel">
            <small>LEVEL UP</small>
            <strong>MOVE TO SCALING TEAM</strong>
          </div>

          <div className="runnerBody">
            <svg viewBox="0 0 130 130" aria-hidden="true">
              <defs>
                <linearGradient id="runnerGradient" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#ffffff" />
                  <stop offset="100%" stopColor="#dbeafe" />
                </linearGradient>
              </defs>

              <circle
                className="head"
                cx="73"
                cy="22"
                r="10"
                fill="url(#runnerGradient)"
              />

              <path
                className="torso"
                d="M68 35 C60 45 56 56 54 68 L72 76 C78 62 82 49 84 41 C82 36 75 33 68 35Z"
                fill="url(#runnerGradient)"
              />

              <path
                className="armBack"
                d="M63 43 L42 58"
                stroke="#ffffff"
                strokeWidth="8"
                strokeLinecap="round"
              />

              <path
                className="armFront"
                d="M78 43 L99 56"
                stroke="#ffffff"
                strokeWidth="8"
                strokeLinecap="round"
              />

              <path
                className="legBack"
                d="M58 70 L38 100"
                stroke="#ffffff"
                strokeWidth="10"
                strokeLinecap="round"
              />

              <path
                className="legFront"
                d="M69 73 L95 96"
                stroke="#ffffff"
                strokeWidth="10"
                strokeLinecap="round"
              />

              <path
                d="M28 101 L43 101"
                stroke="#ff7a00"
                strokeWidth="7"
                strokeLinecap="round"
              />

              <path
                d="M91 99 L108 99"
                stroke="#ff7a00"
                strokeWidth="7"
                strokeLinecap="round"
              />
            </svg>

            <div className="runnerGlow" />
          </div>
        </div>
      </div>

      <style jsx>{`
        .scaleBanner {
          position: relative;
          min-height: 250px;
          overflow: hidden;
          border-radius: 26px;
          margin: 0 0 26px;
          padding: 34px 38px;
          display: grid;
          grid-template-columns: minmax(340px, 0.9fr) minmax(440px, 1.1fr);
          align-items: center;
          gap: 28px;
          color: #fff;
          background:
            linear-gradient(135deg, #07111f 0%, #0b1930 48%, #102c63 100%);
          border: 1px solid rgba(255,255,255,.08);
          box-shadow:
            0 24px 70px rgba(15,23,42,.22),
            inset 0 1px 0 rgba(255,255,255,.05);
        }

        .ambient {
          position: absolute;
          border-radius: 999px;
          filter: blur(70px);
          pointer-events: none;
        }

        .ambientOne {
          width: 320px;
          height: 320px;
          right: -60px;
          top: -120px;
          background: rgba(37,99,235,.28);
        }

        .ambientTwo {
          width: 220px;
          height: 220px;
          left: 36%;
          bottom: -150px;
          background: rgba(255,122,0,.13);
        }

        .gridOverlay {
          position: absolute;
          inset: 0;
          opacity: .08;
          background-image:
            linear-gradient(rgba(255,255,255,.24) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,.24) 1px, transparent 1px);
          background-size: 34px 34px;
          mask-image: linear-gradient(to right, transparent, #000 45%, #000);
        }

        .copy {
          position: relative;
          z-index: 4;
        }

        .eyebrow {
          display: inline-flex;
          align-items: center;
          gap: 9px;
          font-size: 11px;
          font-weight: 800;
          letter-spacing: .16em;
          color: #93c5fd;
          margin-bottom: 15px;
        }

        .liveDot {
          width: 7px;
          height: 7px;
          border-radius: 999px;
          background: #22c55e;
          box-shadow: 0 0 0 6px rgba(34,197,94,.1);
        }

        h2 {
          margin: 0;
          max-width: 470px;
          font-size: clamp(31px, 3vw, 46px);
          line-height: .98;
          letter-spacing: -.045em;
          font-weight: 850;
        }

        h2 span {
          display: block;
          margin-top: 7px;
          color: #ff8a1f;
        }

        p {
          margin: 17px 0 22px;
          max-width: 430px;
          color: #aebbd0;
          font-size: 14px;
          line-height: 1.6;
        }

        .miniStats {
          display: flex;
          align-items: center;
          gap: 13px;
        }

        .miniStats div {
          display: flex;
          align-items: baseline;
          gap: 6px;
        }

        .miniStats strong {
          color: #fff;
          font-size: 12px;
        }

        .miniStats span {
          color: #8190a9;
          font-size: 11px;
          font-weight: 700;
        }

        .miniStats i {
          width: 22px;
          height: 1px;
          background: rgba(255,255,255,.14);
        }

        .motionZone {
          position: relative;
          height: 190px;
          z-index: 3;
        }

        .trackGlow {
          position: absolute;
          left: 4%;
          right: 3%;
          bottom: 40px;
          height: 2px;
          background: linear-gradient(
            90deg,
            rgba(255,255,255,.02),
            rgba(96,165,250,.5),
            rgba(255,122,0,.85)
          );
          box-shadow: 0 0 20px rgba(37,99,235,.24);
        }

        .checkpoint {
          position: absolute;
          bottom: 31px;
          width: 18px;
          height: 18px;
          border-radius: 999px;
          background: #0b1930;
          border: 3px solid #487ee8;
          box-shadow: 0 0 0 7px rgba(72,126,232,.08);
        }

        .checkpoint span {
          position: absolute;
          bottom: -30px;
          left: 50%;
          transform: translateX(-50%);
          color: #71809a;
          font-size: 9px;
          font-weight: 800;
          letter-spacing: .08em;
        }

        .checkpointOne { left: 13%; }
        .checkpointTwo { left: 48%; }
        .checkpointThree {
          right: 2%;
          border-color: #ff7a00;
          box-shadow: 0 0 0 7px rgba(255,122,0,.1);
        }

        .runnerTravel {
          position: absolute;
          left: 3%;
          bottom: 44px;
          width: 235px;
          height: 125px;
          animation: travel 7.2s cubic-bezier(.45,.02,.45,.98) infinite;
          will-change: transform;
        }

        .runnerBody {
          position: absolute;
          right: 0;
          bottom: 0;
          width: 108px;
          height: 108px;
          animation: bodyFloat .42s ease-in-out infinite alternate;
        }

        .runnerBody svg {
          width: 100%;
          height: 100%;
          overflow: visible;
          filter: drop-shadow(0 12px 18px rgba(0,0,0,.28));
        }

        .runnerGlow {
          position: absolute;
          left: 42px;
          bottom: 5px;
          width: 58px;
          height: 12px;
          border-radius: 50%;
          background: rgba(32,106,255,.32);
          filter: blur(8px);
          animation: glowPulse .42s ease-in-out infinite alternate;
        }

        .armBack {
          transform-origin: 63px 43px;
          animation: armBack .42s ease-in-out infinite alternate;
        }

        .armFront {
          transform-origin: 78px 43px;
          animation: armFront .42s ease-in-out infinite alternate;
        }

        .legBack {
          transform-origin: 58px 70px;
          animation: legBack .42s ease-in-out infinite alternate;
        }

        .legFront {
          transform-origin: 69px 73px;
          animation: legFront .42s ease-in-out infinite alternate;
        }

        .runnerLabel {
          position: absolute;
          right: 86px;
          top: 13px;
          min-width: 158px;
          padding: 10px 13px;
          border-radius: 13px;
          background: rgba(9,20,39,.68);
          border: 1px solid rgba(255,255,255,.1);
          backdrop-filter: blur(14px);
          box-shadow: 0 12px 34px rgba(0,0,0,.15);
          animation: labelFloat 1.4s ease-in-out infinite alternate;
        }

        .runnerLabel small {
          display: block;
          color: #ff8a1f;
          font-size: 8px;
          font-weight: 900;
          letter-spacing: .15em;
          margin-bottom: 3px;
        }

        .runnerLabel strong {
          display: block;
          color: #fff;
          font-size: 10px;
          letter-spacing: .045em;
          white-space: nowrap;
        }

        .speedLines {
          position: absolute;
          right: 80px;
          bottom: 29px;
          width: 100px;
          height: 42px;
        }

        .speedLines span {
          position: absolute;
          right: 0;
          height: 3px;
          border-radius: 999px;
          background: linear-gradient(90deg, transparent, #ff7a00);
          opacity: .8;
          animation: speed 1s linear infinite;
        }

        .speedLines span:nth-child(1) {
          width: 86px;
          top: 4px;
        }

        .speedLines span:nth-child(2) {
          width: 58px;
          top: 19px;
          animation-delay: -.25s;
        }

        .speedLines span:nth-child(3) {
          width: 72px;
          top: 34px;
          animation-delay: -.5s;
        }

        @keyframes travel {
          0% {
            transform: translateX(-40px);
            opacity: 0;
          }
          7% {
            opacity: 1;
          }
          48% {
            transform: translateX(34%);
          }
          82% {
            opacity: 1;
          }
          100% {
            transform: translateX(calc(100% + 230px));
            opacity: 0;
          }
        }

        @keyframes bodyFloat {
          from { transform: translateY(0) rotate(-1.5deg); }
          to { transform: translateY(-7px) rotate(1.5deg); }
        }

        @keyframes armBack {
          from { transform: rotate(14deg); }
          to { transform: rotate(-19deg); }
        }

        @keyframes armFront {
          from { transform: rotate(-12deg); }
          to { transform: rotate(18deg); }
        }

        @keyframes legBack {
          from { transform: rotate(12deg); }
          to { transform: rotate(-18deg); }
        }

        @keyframes legFront {
          from { transform: rotate(-13deg); }
          to { transform: rotate(16deg); }
        }

        @keyframes glowPulse {
          from {
            transform: scaleX(1);
            opacity: .7;
          }
          to {
            transform: scaleX(.65);
            opacity: .3;
          }
        }

        @keyframes labelFloat {
          from { transform: translateY(0) scale(1); }
          to { transform: translateY(-3px) scale(1.025); }
        }

        @keyframes speed {
          0% {
            transform: translateX(0);
            opacity: .1;
          }
          50% {
            opacity: .9;
          }
          100% {
            transform: translateX(-24px);
            opacity: 0;
          }
        }

        @media (max-width: 980px) {
          .scaleBanner {
            grid-template-columns: 1fr;
            min-height: 410px;
          }

          .motionZone {
            height: 175px;
          }
        }

        @media (max-width: 640px) {
          .scaleBanner {
            padding: 27px 22px;
            border-radius: 20px;
          }

          h2 {
            font-size: 31px;
          }

          .motionZone {
            margin-left: -10px;
            margin-right: -10px;
          }

          .runnerTravel {
            transform: scale(.88);
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .runnerTravel,
          .runnerBody,
          .runnerLabel,
          .speedLines span,
          .runnerGlow,
          .armBack,
          .armFront,
          .legBack,
          .legFront {
            animation: none !important;
          }
        }
      `}</style>
    </section>
  )
}
