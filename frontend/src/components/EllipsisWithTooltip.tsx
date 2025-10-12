import React, { useState } from 'react';
import { Tooltip, message } from 'antd';
import { CopyOutlined } from '@ant-design/icons';

interface EllipsisWithTooltipProps {
  text: string;
  maxWidth?: number;
  showCopyIcon?: boolean;
  children?: React.ReactNode;
}

const EllipsisWithTooltip: React.FC<EllipsisWithTooltipProps> = ({
  text,
  maxWidth,
  showCopyIcon = false,
  children,
}) => {
  const [isHovered, setIsHovered] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text).then(() => {
      message.success('已复制到剪贴板');
    }).catch(() => {
      message.error('复制失败');
    });
  };

  const content = children || text;

  return (
    <Tooltip title={text} placement="topLeft">
      <div
        style={{
          width: '100%',
          maxWidth: maxWidth || '100%',
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          lineHeight: '1.5',
          height: 'auto',
        }}
        onClick={handleCopy}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <span
          style={{
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            minWidth: 0,
            flex: 1,
          }}
        >
          {content}
        </span>
        {showCopyIcon && isHovered && (
          <CopyOutlined
            style={{
              fontSize: '12px',
              color: '#999',
              flexShrink: 0,
            }}
          />
        )}
      </div>
    </Tooltip>
  );
};

export default EllipsisWithTooltip;
